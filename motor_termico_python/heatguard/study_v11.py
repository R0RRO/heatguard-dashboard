"""HeatGuard v0.11: auditoría observacional y diagnóstico de modelos.

Usa pares WBGT japoneses (globo medido, Tw calculado) y reanálisis regional.
NO es validación física del clip ni permite alertas ocupacionales.
No calibra sobre días de prueba. Los datos suministrados por el usuario siguen
siendo archivos cuya autenticidad externa no fue comprobada independientemente.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
from statistics import mean
from collections import defaultdict

from .japan_api_v09 import normalize_observed, sha256_json
from .weather_history_v07 import normalize_openmeteo, history_url, fetch_json as fetch_weather
from .independent_validation_v09 import pair_and_predict
from .benchmark_v10 import errors_metrics, metrics_groups, bootstrap_day_mae_ci
from .ono_v09 import wbgt_ono

STATION = 44132
# Coordenada del RECINTO Koishikawa, NO medida con GPS del instrumento WBGT.
SITE_PROXY = (35.718547, 139.746464)
ORIGINAL_QUERY = (35.692, 139.750)
HIGH_C = 28.0  # Umbral de investigación, NO umbral clínico u ocupacional.
FEATURES = ('air_temperature_c','relative_humidity_pct','solar_w_m2',
            'wind_speed_10m_m_s','pressure_hpa')


def jst_hour(ts: str) -> int:
    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
    return (dt + timedelta(hours=9)).hour


def add_weather_features(pairs: list[dict], weather: list[dict]):
    index = {x['timestamp_utc']:x for x in weather}
    result = []
    for p in pairs:
        x = index.get(p['timestamp_utc'])
        if x is None: continue
        row = {**p, **{k:float(x[k]) for k in FEATURES}, 'hour_jst':jst_hour(p['timestamp_utc'])}
        result.append(row)
    return result


def split_days(rows: list[dict], *, train_days: int = 9):
    days = sorted(set(p['jst_day'] for p in rows))
    if len(days)<train_days+3:
        raise ValueError(f'Mínimo {train_days+3} días separados; recibidos {len(days)}')
    training = set(days[:train_days]); testing=set(days[train_days:])
    return ([p for p in rows if p['jst_day'] in training],
            [p for p in rows if p['jst_day'] in testing],
            {'train_days':sorted(training),'test_days':sorted(testing)})


def safety_diagnostics(rows: list[dict], *, threshold: float = HIGH_C) -> dict:
    if not rows: return {'status':'no_rows'}
    high = [x for x in rows if float(x['reference_c'])>=threshold]
    low  = [x for x in rows if float(x['reference_c'])<threshold]
    fn=[x for x in high if float(x['model_c'])<threshold]
    fp=[x for x in low if float(x['model_c'])>=threshold]
    return {
        'threshold_c_research_only':threshold,'n':len(rows),'n_reference_ge_threshold':len(high),
        'false_low_count':len(fn), 'false_low_fraction_given_high':round(len(fn)/len(high),4) if high else None,
        'false_high_count':len(fp), 'false_high_fraction_given_low':round(len(fp)/len(low),4) if low else None,
        'high_reference_metrics':errors_metrics(high),
    }


def feature_matrix(rows: list[dict]):
    return [[r['air_temperature_c'],r['relative_humidity_pct'],r['solar_w_m2'],
             r['wind_speed_10m_m_s'],r['pressure_hpa'],r['model_c'],
             math.sin(2*math.pi*r['hour_jst']/24),math.cos(2*math.pi*r['hour_jst']/24)] for r in rows]


def with_predictions(rows: list[dict], preds: list[float]) -> list[dict]:
    assert len(rows)==len(preds)
    return [{**r,'model_c':round(float(y),5),
             'error_c':round(float(y)-float(r['reference_c']),5)} for r,y in zip(rows,preds)]


def compare_predeclared_corrections(train:list[dict],test:list[dict]):
    # Nunca elige hiperparámetros usando el conjunto de test.
    if not train or not test: raise ValueError('Holdout vacío')
    baseline=errors_metrics(test)
    bias=mean(float(r['error_c']) for r in train)
    after_bias=with_predictions(test, [r['model_c']-bias for r in test])
    output={
        'baseline':{'metrics':baseline,'safety':safety_diagnostics(test)},
        'train_only_global_bias_c':round(bias,5),
        'bias_corrected':{'metrics':errors_metrics(after_bias),'safety':safety_diagnostics(after_bias)},
    }
    predictions={'ono_raw':test,'bias_corrected':after_bias}
    try:
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        from sklearn.linear_model import Ridge
    except ImportError:
        output['ridge_fixed_no_tuning']={'status':'dependency_unavailable','install':'pip install scikit-learn'}
        return output,predictions
    # Modelo de investigación: corrige error; pondera el grupo >=28 en entrenamiento.
    # No produce probabilidades de enfermedad; NO se despliega automáticamente.
    model=make_pipeline(StandardScaler(),Ridge(alpha=10.0))
    model.fit(feature_matrix(train),[-float(r['error_c']) for r in train],
              ridge__sample_weight=[3.0 if float(r['reference_c'])>=HIGH_C else 1.0 for r in train])
    deltas=model.predict(feature_matrix(test))
    adjusted=with_predictions(test,[float(x['model_c'])+float(d) for x,d in zip(test,deltas)])
    output['ridge_fixed_no_tuning']={
       'status':'exploratory_temporal_holdout','training_rows':len(train),
       'test_rows':len(test),'model':'StandardScaler+Ridge(alpha=10); weights high=3; fixed a priori',
       'metrics':errors_metrics(adjusted),'safety':safety_diagnostics(adjusted),
       'no_deployment':True,
    }
    predictions['ridge_fixed_no_tuning']=adjusted
    return output,predictions


def time_shift_solar_experiment(ref:list[dict],weather:list[dict], *, train_days:int=9)->dict:
    """Sensibilidad temporal con preselección de desfase SOLO en train.

    shift=+1 toma radiación de t+1 para WBGT observado en t (no asume corrección).
    Comparación sobre timestamps comunes para evitar sesgos de cobertura.
    """
    byts={x['timestamp_utc']:x for x in weather}
    tslist=[x['timestamp_utc'] for x in weather]
    positions={ts:i for i,ts in enumerate(tslist)}
    shifted={}
    for shift in (-1,0,1):
        data=[]
        for x in weather:
            i=positions[x['timestamp_utc']]+shift
            if not (0<=i<len(weather)):continue
            if datetime.fromisoformat(weather[i]['timestamp_utc'].replace('Z','+00:00')) - datetime.fromisoformat(x['timestamp_utc'].replace('Z','+00:00')) != timedelta(hours=shift):
                continue
            y=dict(x); y['solar_w_m2']=weather[i]['solar_w_m2'];data.append(y)
        pairs,_=pair_and_predict(ref,data,model='ono')
        shifted[shift]={p['timestamp_utc']:p for p in pairs}
    common=set.intersection(*(set(v) for v in shifted.values()))
    if not common:raise ValueError('Sin horas comparables para desfases')
    days=sorted(set(shifted[0][t]['jst_day'] for t in common))
    if len(days)<train_days+3:raise ValueError('Días insuficientes para desfases')
    train_days_set=set(days[:train_days]);test_days_set=set(days[train_days:])
    def take(s,which):return [v for t,v in shifted[s].items() if t in common and v['jst_day'] in which]
    train_maes={str(k):errors_metrics(take(k,train_days_set))['mae_c'] for k in (-1,0,1)}
    best=min((-1,0,1),key=lambda k:(train_maes[str(k)],abs(k)))
    test_metrics={str(k):errors_metrics(take(k,test_days_set)) for k in (-1,0,1)}
    return {'comparison':'solar hourly alignment sensitivity (not validated correction)',
            'shift_definition':'solar source time=t+shift hours, all other inputs at t',
            'common_timestamps':len(common),'train_days':sorted(train_days_set),
            'test_days':sorted(test_days_set),'train_mae_c':train_maes,
            'preselected_shift_from_train_only_hours':best,
            'test_metrics_all_shifts_for_research_only':test_metrics,
            'not_authorized_to_change_production_alignment':True}


def optional_liljegren(ref:list[dict],weather:list[dict]):
    try:
        import lwbgt  # noqa
    except ImportError:
        return {'status':'unavailable','reason':'lwbgt no instalado; sin métricas Liljegren'},[]
    pairs,rejected=pair_and_predict(ref,weather,model='liljegren')
    if not pairs:return {'status':'blocked_model_failed','rejected':rejected},[]
    return {'status':'evaluated','n':len(pairs),'metrics':errors_metrics(pairs),
            'high':safety_diagnostics(pairs),'rejected':rejected},pairs


def load_external_model_predictions(path:Path, benchmark_rows:list[dict], *, model_name:str):
    """Predicciones de terceros: estricto pareo por timestamp, sin interpolar."""
    with path.open(newline='',encoding='utf-8-sig') as f:
        reader=csv.DictReader(f)
        if not {'timestamp_utc','wbgt_c'}.issubset(reader.fieldnames or []):
            raise ValueError(f'{model_name}: CSV exige timestamp_utc,wbgt_c')
        idx={}
        for r in reader:
            ts=r['timestamp_utc'];val=float(r['wbgt_c'])
            if ts in idx: raise ValueError(f'{model_name}: hora duplicada')
            if not math.isfinite(val) or not -40<=val<=60:raise ValueError(f'{model_name}: rango inválido')
            idx[ts]=val
    if not idx: raise ValueError('CSV de predicciones vacío')
    return with_predictions([r for r in benchmark_rows if r['timestamp_utc'] in idx],
                            [idx[r['timestamp_utc']] for r in benchmark_rows if r['timestamp_utc'] in idx])


def run(japan:dict,meteorology:dict, *, station:int=STATION,
        ref_lat:float=ORIGINAL_QUERY[0],ref_lon:float=ORIGINAL_QUERY[1],
        provenance:str='user_supplied_offline_not_reauthenticated',
        kong_csv:Path|None=None, train_days:int=9):
    refs, qc=normalize_observed(japan,station_no=station,site_id='JP_TOKYO',
                               latitude_deg=ref_lat,longitude_deg=ref_lon)
    weather=normalize_openmeteo(meteorology,session_id='v11_existing_offline')
    pairs,rejected=pair_and_predict(refs,weather,model='ono')
    enriched=add_weather_features(pairs,weather)
    training,testing,split=split_days(enriched,train_days=train_days)
    comp,predictions=compare_predeclared_corrections(training,testing)
    lag=time_shift_solar_experiment(refs,weather,train_days=train_days)
    lil,lilrows=optional_liljegren(refs,weather)
    models={'ono':{'status':'evaluated','metrics':metrics_groups(enriched),
                   'bootstrap_by_day':bootstrap_day_mae_ci(enriched),
                   'research_threshold':safety_diagnostics(enriched),
                   'rejected':rejected},
            'liljegren':lil,
            'kong_huber':{'status':'not_evaluated','reason':'requiere predicciones externas verificables; código de autores no se redistribuye'}}
    if kong_csv:
        kh=load_external_model_predictions(kong_csv,enriched,model_name='kong_huber')
        if len(kh)<48:
            models['kong_huber']={'status':'blocked_insufficient_matching_hours','matched_hours':len(kh)}
        else:
            models['kong_huber']={'status':'user_computed_predictions_unverified','n':len(kh),
                                   'metrics':errors_metrics(kh),'research_threshold':safety_diagnostics(kh),
                                   'warning':'Verificar versión, unidades, licencia y metadatos del cómputo externo'}
    metadata={'source_provenance':provenance,'japan_json_sha256':sha256_json(japan),
         'weather_json_sha256':sha256_json(meteorology),
         'station':station,'reference_method':'Japan MOE; Tg observed + Tw psychrometric computed',
         'reference_quality_filter':'class=1, WI=4','reference_quality_counts':qc,
         'site_position_used_for_pairing':[ref_lat,ref_lon],
         'site_coordinates_verified_exact_instrument':False,
         'garden_geographic_proxy':list(SITE_PROXY),
         'weather_grid_lat_lon':[meteorology.get('latitude'),meteorology.get('longitude')],
         'label':'independent validation of ENVIRONMENTAL MODEL on external data, not physical clip',
         'not_ISO_7243_compliance':True,'high_threshold_for_research_only_c':HIGH_C,
         'holdout_contamination_warning':'Investigación exploratoria sobre Tokio ya revisado; test reservado temporalmente, pero decisiones futuras requieren nuevas fechas/sitios.'}
    report={'status':'exploratory_observational_software_evaluation',
            'metadata':metadata,'n_reference_pairs':len(enriched), 'split':split,
            'models':models,'corrections_test_only':comp,
            'solar_time_alignment_sensitivity':lag,
            'research_recommendation':'Priorizar investigación de subestimación >=28 °C, no desplegar Ridge ni convertir 28°C en umbral de seguridad.'}
    return report,predictions


def save(report:dict,pred:dict,output:Path):
    output.mkdir(parents=True,exist_ok=True)
    (output/'reporte_v11.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    keys=['timestamp_utc','jst_day','reference_c','model_c','error_c','solar_w_m2','wind_speed_10m_m_s']
    for name,items in pred.items():
        with (output/f'{name}_test.csv').open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(items)
    model=report['models']['ono']['metrics']['all']
    out=['# HeatGuard v0.11 — Estudio de Tokio (solo software)','',
         f"**Estado:** {report['status']}. **Horas comparadas:** {report['n_reference_pairs']}.",
         f"**MAE Ono:** {model['mae_c']:.3f} °C; **RMSE:** {model['rmse_c']:.3f} °C.",'',
         '## Correcciones en días reservados',
         '| Variante | MAE °C | Sesgo °C | Subestimación >1°C | Falsos bajos a corte exploratorio 28°C |',
         '|---|---:|---:|---:|---:|']
    for key,x in report['corrections_test_only'].items():
        if isinstance(x,dict) and 'metrics' in x:
            m=x['metrics'];s=x['safety'];out.append(f"| {key} | {m['mae_c']:.3f} | {m['bias_model_minus_reference_c']:.3f} | {m['underestimation_gt_1c_fraction']:.1%} | {s['false_low_count']}/{s['n_reference_ge_threshold']} |")
    out += ['', '## Procedencia y límites',
             '- Archivos originales aportados por el usuario: consistencia interna verificada, autenticidad no confirmada por descarga independiente.',
             '- La estación 44132 se encuentra en Koishikawa. El proxy del jardín no representa coordenadas exactas del sensor.',
             '- La evaluación base usa meteorología regional (reenálisis) y coordenadas históricas de la consulta original.',
             '- Referencia japonesa no equivale a WBGT ISO íntegramente instrumental.',
             '- El conjunto de prueba no debe utilizarse para elegir el mejor modelo y reportarlo como validación externa.',
             '- Los modelos supervisados son de laboratorio y no están autorizados para activar alertas.',
             '- La elección de sensor se hará con mediciones físicas posteriores, no solo ablations.', '']
    (output/'REPORTE_v11.md').write_text('\n'.join(out),encoding='utf-8')
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,ax=plt.subplots(figsize=(10.4,4.4))
        base=pred['ono_raw']; x=list(range(len(base)))
        ax.plot(x,[z['reference_c'] for z in base],label='Referencia japonesa',linewidth=1.6)
        ax.plot(x,[z['model_c'] for z in base],label='Ono regional',linewidth=1.2)
        if 'ridge_fixed_no_tuning' in pred:
            ax.plot(x,[z['model_c'] for z in pred['ridge_fixed_no_tuning']],label='Ridge experimental',linewidth=1,alpha=.8)
        ax.set(title='Holdout temporal: últimos días (NO validación del clip)',xlabel='Hora relativa en evaluación',ylabel='WBGT [°C]')
        ax.legend(loc='best');fig.tight_layout();fig.savefig(output/'holdout_comparacion.png',dpi=155);plt.close(fig)
    except ImportError:pass


def main():
    p=argparse.ArgumentParser(description='HeatGuard v0.11: validación exploratoria observacional de Tokio')
    p.add_argument('--japan-json',default='data/tokyo_2025_aug_user_run/japon_respuesta.json')
    p.add_argument('--weather-json',default='data/tokyo_2025_aug_user_run/openmeteo_respuesta.json')
    p.add_argument('--download-weather',action='store_true',help='Descarga meteorología del recinto Koishikawa (requiere internet); nunca inventa datos')
    p.add_argument('--site-lat',type=float,default=SITE_PROXY[0])
    p.add_argument('--site-lon',type=float,default=SITE_PROXY[1])
    p.add_argument('--reference-lat',type=float,default=ORIGINAL_QUERY[0])
    p.add_argument('--reference-lon',type=float,default=ORIGINAL_QUERY[1])
    p.add_argument('--start',default='2025-08-01');p.add_argument('--end',default='2025-08-14')
    p.add_argument('--train-days',type=int,default=9)
    p.add_argument('--kong-csv',type=Path)
    p.add_argument('--out',default='results/v11_tokio_auditoria')
    a=p.parse_args()
    japan=json.loads(Path(a.japan_json).read_text(encoding='utf-8'))
    if a.download_weather:
        first,last=date.fromisoformat(a.start),date.fromisoformat(a.end)
        url=history_url(a.site_lat,a.site_lon,(first-timedelta(days=1)).isoformat(),(last+timedelta(days=1)).isoformat())
        print('Descargando nuevos datos para proxy de recinto (NO coordenadas exactas del instrumento).')
        try:weather=fetch_weather(url)
        except Exception as ex:raise SystemExit(f'Descarga fallida: {ex}; no se generaron métricas de nuevas coordenadas.')
    else:
        weather=json.loads(Path(a.weather_json).read_text(encoding='utf-8'))
    provenance='new_weather_api_query_garden_proxy' if a.download_weather else 'user_supplied_offline_unverified'
    # Si se descargó nueva celda regional, usa el proxy como punto de pareo, manteniendo advertencia de inexactitud.
    rlat= a.site_lat if a.download_weather else a.reference_lat
    rlon= a.site_lon if a.download_weather else a.reference_lon
    report,pred=run(japan,weather,ref_lat=rlat,ref_lon=rlon,
                   provenance=provenance,kong_csv=a.kong_csv,train_days=a.train_days)
    target=Path(a.out);save(report,pred,target)
    if a.download_weather:
        (target/'openmeteo_nueva_celda.json').write_text(json.dumps(weather,ensure_ascii=False),encoding='utf-8')
    print('Guardado:',target)
    print('Ono MAE:',report['models']['ono']['metrics']['all']['mae_c'],'°C')
    for name,metrics in report['corrections_test_only'].items():
        if isinstance(metrics,dict) and 'metrics' in metrics:
            print(name,metrics['metrics']['mae_c'],'°C; falsos bajos 28°C:',metrics['safety']['false_low_count'])
    print('Liljegren:',report['models']['liljegren']['status'])
    print('Kong-Huber:',report['models']['kong_huber']['status'])
    print('NO: esta salida no valida ISO ni el clip.')

if __name__=='__main__':main()
