"""Simulacion retrospectiva de un ancla WBGT por sitio. NO extrapolar a clips reales.

Entrenar modelo en otros sitios hasta el 14 de agosto, calibrar solo con
referencias del sitio nuevo en dias 15..(14+n), y evaluar 22..31 sin utilizar
sus etiquetas durante la calibracion. Los anclajes no son datos de un sensor
fisico en faena, son etiquetas meteorologicas japonesas del propio sitio.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from .uncertainty_ml_v21 import (
    SITES,ALPHA,RESEARCH_THRESHOLD,finite_sample_upper_quantile, features, models, partitions, scores, validate,
)


def run(csv_path, out_dir):
    df=pd.read_csv(csv_path)
    validate(df,'regional')
    rows=[];paired=[]
    dates=pd.to_datetime(df.jst_day)
    for heldout in SITES:
        tr,other_cal,test=partitions(df,'regional',heldout)
        xtr=features(tr,'regional').to_numpy()
        model=models()['hgb']
        model.fit(xtr,(tr.reference_c-tr.ono_c).to_numpy())
        pred_test_base=test.ono_c.to_numpy()
        pred_test_hgb=pred_test_base+model.predict(features(test,'regional').to_numpy())
        obs=test.reference_c.to_numpy()
        for n_days in [0,1,3,7]:
            if n_days==0:
                anchor_cal=other_cal
            else:
                cutoff=pd.Timestamp('2025-08-14')+pd.Timedelta(days=n_days)
                anchor_cal=df[(df.site_id==heldout)&(dates>pd.Timestamp('2025-08-14'))&(dates<=cutoff)].copy()
            if anchor_cal.empty:raise ValueError('sin datos anchor')
            base_cal=anchor_cal.ono_c.to_numpy()
            hgb_cal=base_cal+model.predict(features(anchor_cal,'regional').to_numpy())
            for method,cal_pred,test_pred in [('ono',base_cal,pred_test_base),('hgb',hgb_cal,pred_test_hgb)]:
                residual=anchor_cal.reference_c.to_numpy()-cal_pred
                # No lo usamos para decidir riesgos: offset robusto para ESTIMADO CENTRAL.
                b=float(np.median(residual))
                point=test_pred+(b if n_days>0 else 0.)
                # Margen de cuantiles para la cota superior (no es seguridad garantizada).
                adjusted_cal=cal_pred+(b if n_days>0 else 0.)
                margin=finite_sample_upper_quantile(anchor_cal.reference_c.to_numpy()-adjusted_cal)
                upper=point+margin
                for label,pred in [('central',point),('upper90_research',upper)]:
                    met=scores(obs,pred)
                    met.update({'method':method,'anchor_days':n_days,'heldout_site':heldout,'variant':label,
                        'anchor_n':len(anchor_cal),'point_bias_c':round(b if n_days>0 else 0.,4),
                        'upper_margin_c':round(margin,4) if label=='upper90_research' else None})
                    if label=='upper90_research':
                        met['upper_coverage']=round(float(np.mean(pred>=obs)),4)
                        met['mean_excess_vs_ono_c']=round(float(np.mean(pred-pred_test_base)),4)
                    rows.append(met)
                    paired.append(pd.DataFrame({'site_id':heldout,'timestamp_utc':test.timestamp_utc,'reference_c':obs,
                        'model':method,'anchor_days':n_days,'variant':label,'prediction_c':pred}))
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    met=pd.DataFrame(rows)
    predictions=pd.concat(paired,ignore_index=True)
    met.to_csv(out/'metricas_anclaje_por_estacion.csv',index=False)
    predictions.to_csv(out/'predicciones_anclaje.csv',index=False)
    summary=[]
    for (method,days,variant),g in predictions.groupby(['model','anchor_days','variant']):
        allmet=scores(g.reference_c.to_numpy(),g.prediction_c.to_numpy())
        if variant=='upper90_research':
            allmet['upper_coverage']=round(float(np.mean(g.prediction_c>=g.reference_c)),4)
        summary.append({'method':method,'anchor_days':int(days),'variant':variant,**allmet})
    report={'status':'EXPLORATORY_SIMULATED_SITE_REFERENCE_NOT_DEVICE',
      'method':'Train other 3 sites Aug1-14; anchor target site first 0,1,3,7 days from Aug15; evaluate heldout target site Aug22-31; never use test labels for correction.',
      'anchor_kind':'Japanese reference WBGT composite with shared air measurements; NO workplace instrument deployed',
      'n_sites':4,'last_test_days':10,
      'limitations':['Already studied historical dates; retrospective comparison',
        'New worksite, indoor heat, solar and local microclimate not represented',
        'No statistical 90% coverage guarantee under time/site distribution shifts',
        'Fixed reference station only; transfer from site reference to moving workers NOT evaluated',
        'Reference is not fully ISO 7243 natural wet-bulb instrumentation'],
      'summary':summary}
    (out/'REPORTE_ANCLAJE_V021.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return report,met,predictions


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--csv',default='research_data/observaciones_japon_2025_agosto.csv')
    p.add_argument('--out',default='results/v21_site_anchor')
    a=p.parse_args()
    r,_,_=run(a.csv,a.out)
    print(json.dumps({'status':r['status'],'out':a.out,'summary':r['summary']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
