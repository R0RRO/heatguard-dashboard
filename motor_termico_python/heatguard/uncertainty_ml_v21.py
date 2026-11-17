"""HeatGuard v0.21: benchmark retrospectivo de prediccion central + cota superior.

NO ES UN SISTEMA DE ALERTAS, NO ES UN WBGT ISO 7243, NO ES CALIBRACION DEL CLIP.

Diseño: tres conjuntos disjuntos por fecha; cuatro folds espaciales;
quantil superior residual y conformal de una cola. Fuentes externas (NO BLE).
Usar siempre el fichero de origen y los manifiestos de la v0.20.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

RESEARCH_THRESHOLD = 28.0
ALPHA = 0.10  # coverage objetivo solo si se cumplen supuestos de intercambiabilidad
SITES = ('JP_TOKYO', 'JP_OSAKA', 'JP_FUKUOKA', 'JP_SAPPORO')
TRAIN_LAST = '2025-08-14'
CAL_FIRST, CAL_LAST = '2025-08-15', '2025-08-21'
TEST_FIRST = '2025-08-22'


def sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()


def validate(df: pd.DataFrame, mode: str):
    common = {'site_id', 'timestamp_utc', 'jst_day', 'reference_c', 'hour_sin', 'hour_cos'}
    if mode == 'regional':
        required = common | {'ono_c','liljegren_c','temperature_c','relative_humidity_pct', 'solar_w_m2','wind_10m_m_s','pressure_hpa','air_data_origin'}
        allowed = set(SITES)
        provenance = ('air_data_origin','open_meteo_reanalysis')
    elif mode == 'local':
        required = common | {'ono_jma_c','liljegren_jma_c','air_temperature_jma_c','relative_humidity_jma_pct','solar_external_w_m2','wind_external_10m_m_s','pressure_jma_hpa','air_origin','solar_wind_origin'}
        allowed = {'JP_FUKUOKA'}
        provenance = ('air_origin','jma_observatory_measured')
    else:
        raise ValueError('mode invalido')
    if not required.issubset(df.columns): raise ValueError(f'Columnas ausentes: {sorted(required-set(df.columns))}')
    if df.empty or df.duplicated(['site_id','timestamp_utc']).any(): raise ValueError('Tabla vacia o registros duplicados')
    if set(df.site_id) != allowed: raise ValueError('Estaciones inesperadas')
    if not (df[provenance[0]]==provenance[1]).all(): raise ValueError('Procedencia de sensores incompatible')
    if mode=='local' and not (df.solar_wind_origin=='open_meteo_reanalysis').all(): raise ValueError('Procedencia solar/viento incompatible')
    if not (pd.to_datetime(df.jst_day).between('2025-08-01','2025-08-31')).all(): raise ValueError('Fechas inesperadas')
    numeric=df.select_dtypes('number')
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():raise ValueError('Valores no finitos')
    if not df.reference_c.between(-30,65).all():raise ValueError('Referencia fuera de rango')
    if mode=='local' and len(df)!=744: raise ValueError('Esperabamos 744 horas JMA para este experimento')
    if mode=='regional' and len(df)!=2976: raise ValueError('Esperabamos 2976 horas de cuatro estaciones')
    return True


def features(df: pd.DataFrame, mode: str) -> pd.DataFrame:
    """Variables disponibles al predecir; ninguna usa la referencia."""
    if mode=='regional':
        ono, physical = df.ono_c, df.liljegren_c
        t, rh = df.temperature_c, df.relative_humidity_pct
        solar, wind, pressure = df.solar_w_m2, df.wind_10m_m_s, df.pressure_hpa
    else:
        ono, physical=df.ono_jma_c,df.liljegren_jma_c
        t,rh=df.air_temperature_jma_c,df.relative_humidity_jma_pct
        solar,wind,pressure=df.solar_external_w_m2,df.wind_external_10m_m_s,df.pressure_jma_hpa
    # Ecuacion de Tetens: vapor saturante aproximado (kPa), dentro de dominio meteorologico.
    esat=0.61078*np.exp((17.27*t)/(t+237.3))
    ea=esat*rh/100.0
    vpd=np.maximum(0,esat-ea)
    arr=pd.DataFrame({
        'ono':ono,'liljegren':physical,
        'model_disagreement':physical-ono,
        'air_temperature':t,'rh':rh,'vapor_pressure_kpa':ea,'vpd_kpa':vpd,
        'radiation_wm2':solar,'wind_10m_ms':wind,
        'solar_over_wind':solar/(wind+0.5),
        'temp_x_rh':t*rh/100,
        'pressure_hpa':pressure,
        'hour_sin':df.hour_sin,'hour_cos':df.hour_cos,
    },index=df.index)
    if not np.isfinite(arr.to_numpy()).all(): raise ValueError('Variables fisicas no finitas')
    return arr


def partitions(df:pd.DataFrame,mode:str,heldout:str|None):
    dates=pd.to_datetime(df.jst_day)
    if mode=='regional':
        if heldout not in SITES: raise ValueError('Estacion de prueba no valida')
        tr=(dates<=TRAIN_LAST)&(df.site_id!=heldout)
        ca=dates.between(CAL_FIRST,CAL_LAST)&(df.site_id!=heldout)
        te=(dates>=TEST_FIRST)&(df.site_id==heldout)
    else:
        if heldout is not None:raise ValueError('No hay prueba espacial usando una estacion local')
        tr=dates<=TRAIN_LAST
        ca=dates.between(CAL_FIRST,CAL_LAST)
        te=dates>=TEST_FIRST
    train,cal,test=[df.loc[m].copy() for m in (tr,ca,te)]
    if min(len(train),len(cal),len(test))==0: raise ValueError('Una particion esta vacia')
    # Las fechas de train, calibracion y test son mutuamente exclusivas.
    day_sets=[set(x.jst_day) for x in (train,cal,test)]
    if any(day_sets[i]&day_sets[j] for i in range(3) for j in range(i+1,3)):raise ValueError('Contaminacion temporal')
    if mode=='regional' and any(heldout in set(x.site_id) for x in (train,cal)):raise ValueError('Contaminacion espacial')
    return train,cal,test


def finite_sample_upper_quantile(scores, alpha=ALPHA):
    """Cuantil conformal unilateral: ceil((n+1)*(1-alpha))-esimo ordenado.

    Para objetivo de 90% solo hay garantia marginal si calibracion y prueba
    son intercambiables; no aplicable a estaciones nuevas, que tienen shift.
    """
    z=np.asarray(scores,dtype=float)
    if len(z)<20 or not np.isfinite(z).all():raise ValueError('Calibracion invalida')
    k=math.ceil((len(z)+1)*(1-alpha))
    if k>len(z):return float('inf')
    return max(0.,float(np.sort(z)[k-1]))


def scores(ref, pred):
    ref,pred=np.asarray(ref),np.asarray(pred)
    if len(ref)!=len(pred) or len(ref)==0 or not np.isfinite(ref).all() or not np.isfinite(pred).all(): raise ValueError('Forma o datos invalidos')
    err=pred-ref; high=ref>=RESEARCH_THRESHOLD; low=~high
    return {
        'n':int(len(ref)),'n_high':int(high.sum()),
        'mae_c':round(float(np.mean(np.abs(err))),4),
        'rmse_c':round(float(np.sqrt(np.mean(err**2))),4),
        'bias_c':round(float(np.mean(err)),4),
        'false_low_n':int(np.sum(high & (pred<RESEARCH_THRESHOLD))),
        'false_high_n':int(np.sum(low & (pred>=RESEARCH_THRESHOLD))),
        'false_low_rate_given_high':round(float(np.mean(pred[high]<RESEARCH_THRESHOLD)),4) if high.any() else None,
        'false_high_rate_given_low':round(float(np.mean(pred[low]>=RESEARCH_THRESHOLD)),4) if low.any() else None,
        'under_gt1_when_high_n':int(np.sum(high & (err<-1))),
        'under_gt2_when_high_n':int(np.sum(high & (err<-2))),
        'high_mae_c':round(float(np.mean(np.abs(err[high]))),4) if high.any() else None,
    }


def models():
    return {
        'ridge':make_pipeline(StandardScaler(),Ridge(alpha=100)),
        'hgb':HistGradientBoostingRegressor(max_iter=140,learning_rate=.045,max_leaf_nodes=7,min_samples_leaf=40,l2_regularization=30,random_state=42),
        'q90':HistGradientBoostingRegressor(loss='quantile',quantile=.90,max_iter=140,learning_rate=.045,max_leaf_nodes=7,min_samples_leaf=40,l2_regularization=30,random_state=42),
    }


def one_fold(df,mode,heldout=None, out=None):
    tr,ca,te=partitions(df,mode,heldout)
    xtr=features(tr,mode).to_numpy()
    xca=features(ca,mode).to_numpy()
    xte=features(te,mode).to_numpy()
    obase='ono_c' if mode=='regional' else 'ono_jma_c'
    lbase='liljegren_c' if mode=='regional' else 'liljegren_jma_c'
    ytr=(tr.reference_c-tr[obase]).to_numpy()
    fitted=models()
    for model in fitted.values(): model.fit(xtr,ytr)
    base_cal=ca[obase].to_numpy()
    base_test=te[obase].to_numpy()
    med_cal=base_cal+fitted['hgb'].predict(xca)
    med_test=base_test+fitted['hgb'].predict(xte)
    ridge_test=base_test+fitted['ridge'].predict(xte)
    q90_cal=base_cal+fitted['q90'].predict(xca)
    q90_test=base_test+fitted['q90'].predict(xte)
    ubase=finite_sample_upper_quantile(ca.reference_c.to_numpy()-base_cal)
    umed=finite_sample_upper_quantile(ca.reference_c.to_numpy()-med_cal)
    uq=finite_sample_upper_quantile(ca.reference_c.to_numpy()-q90_cal)
    pred={
        'ono_c':base_test,
        'liljegren_c':te[lbase].to_numpy(),
        'ridge_point_c':ridge_test,
        'hgb_point_c':med_test,
        'ono_upper90_c':base_test+ubase,
        'hgb_upper90_c':med_test+umed,
        'quantile_upper90_c':q90_test+uq,
    }
    ref=te.reference_c.to_numpy()
    metrics=[]
    for name,values in pred.items():
        m=scores(ref,values)
        if 'upper90' in name:
            m['upper_coverage']=round(float(np.mean(values>=ref)),4)
            m['mean_excess_above_ono_c']=round(float(np.mean(values-base_test)),4)
            m['bound_not_safety_certified']=True
        metrics.append({'domain':mode,'test_site':heldout if heldout else 'JP_FUKUOKA','kind':'upper_research_only' if 'upper90' in name else 'point', 'method':name,**m})
    frame=te[['site_id','timestamp_utc','jst_day','reference_c']].copy()
    frame['domain']=mode;frame['fold']=heldout if heldout else 'local_fukuoka'
    for key,values in pred.items():frame[key]=values
    infos={
        'domain':mode, 'heldout_site':heldout if heldout else 'local_fukuoka',
        'train_n':len(tr),'cal_n':len(ca),'test_n':len(te),
        'train_sites':sorted(tr.site_id.unique().tolist()),
        'cal_sites':sorted(ca.site_id.unique().tolist()),
        'test_sites':sorted(te.site_id.unique().tolist()),
        'train_dates':['2025-08-01',TRAIN_LAST],
        'calibration_dates':[CAL_FIRST,CAL_LAST],
        'test_dates':[TEST_FIRST,'2025-08-31'],
        'conformal_q_c':{'ono':round(ubase,4),'hgb':round(umed,4),'quantile':round(uq,4)},
    }
    if out is not None:
        import joblib
        out=Path(out); out.mkdir(parents=True,exist_ok=True)
        joblib.dump({'models':fitted,'feature_columns':features(tr,mode).columns.tolist(),
                     'meta':{'status':'RESEARCH_ONLY_NO_DEPLOY','training_domain':mode,'fold':heldout,
                             'calibration':infos['conformal_q_c'],'not_clip_measurement':True,
                             'not_normative_wbgt':True,'not_safety_bound':True}}, out/'modelos_exploratorios.joblib')
    return metrics,frame,infos


def run(regional_csv,local_csv,outdir):
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
    dfr=pd.read_csv(regional_csv); dfl=pd.read_csv(local_csv)
    validate(dfr,'regional');validate(dfl,'local')
    metrics=[];frames=[];folds=[]
    for site in SITES:
        m,f,info=one_fold(dfr,'regional',site,out/'modelos'/site)
        metrics+=m;frames.append(f);folds.append(info)
    m,f,info=one_fold(dfl,'local',None,out/'modelos'/'local_fukuoka')
    metrics+=m;frames.append(f);folds.append(info)
    mdf=pd.DataFrame(metrics);pdf=pd.concat(frames,ignore_index=True)
    mdf.to_csv(out/'metricas_por_fold.csv',index=False)
    pdf.to_csv(out/'predicciones_prueba.csv',index=False)
    # Conteos globales se calculan sobre ejemplos, nunca se promedian tasas por estacion.
    regional=pdf[pdf.domain=='regional']
    aggreg=[]
    for method in ('ono_c','liljegren_c','ridge_point_c','hgb_point_c','ono_upper90_c','hgb_upper90_c','quantile_upper90_c'):
        t=scores(regional.reference_c.to_numpy(),regional[method].to_numpy())
        if 'upper90' in method:
            t['upper_coverage']=round(float(np.mean(regional[method].to_numpy()>=regional.reference_c.to_numpy())),4)
            t['mean_excess_above_ono_c']=round(float(np.mean(regional[method]-regional.ono_c)),4)
        aggreg.append({'method':method,'domain':'regional_unseen_site_last10days',**t})
    report={
        'status':'RETROSPECTIVE_EXPLORATORY_ONLY',
        'source_sha256':{'regional':sha256(regional_csv),'local':sha256(local_csv)},
        'source_domains':['Open-Meteo regional + Japan MOE partially instrumental','JMA onsite air + Open-Meteo wind/solar + Japan MOE partially instrumental'],
        'not_real_clip':True,'not_iso_7243_validation':True,
        'not_safety_decision_system':True,'not_untouched_holdout':True,
        'upper_target_probability':0.90,
        'upper_validity_caveat':'Conformal requires exchangeability; unseen-site distribution shift invalidates marginal guarantees. Observed coverage is reported, never promised.',
        'split':folds,'summary_unseen_site':aggreg,
        'methodology':'Train 1-14 Aug 2025, calibrate 15-21, evaluate 22-31; spatial leave-one-station-out, 4 folds. Additionally Fukuoka local temporal split.',
        'research_threshold_only_c':RESEARCH_THRESHOLD,
    }
    (out/'REPORTE_V021.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return report,mdf,pdf


def main():
    p=argparse.ArgumentParser(description='Benchmarck ML e incertidumbre SOLO INVESTIGACION')
    p.add_argument('--regional',default='research_data/observaciones_japon_2025_agosto.csv')
    p.add_argument('--local',default='research_data/fukuoka_jma_local_2025_agosto.csv')
    p.add_argument('--out',default='results/v21_quantile')
    args=p.parse_args()
    report,_,_=run(args.regional,args.local,args.out)
    print(json.dumps({'status':report['status'],'output':args.out,'total_folds':len(report['split']),
        'summary_unseen_site':report['summary_unseen_site']},indent=2,ensure_ascii=False))
if __name__=='__main__':main()
