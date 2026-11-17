"""Protocolo de validación multiestación con métricas por sitio y generalización.

No publica desempeño multiestación con menos de dos sitios con datos observacionales
admisibles. Para prueba de generalización Ridge requiere >= 3 sitios y un número
mínimo de días por sitio. Todos los ejemplos de manifest son plantillas, no datos.
"""
from __future__ import annotations
import argparse,json,csv
from pathlib import Path
from .japan_api_v09 import normalize_observed
from .weather_history_v07 import normalize_openmeteo
from .independent_validation_v09 import pair_and_predict
from .benchmark_v10 import errors_metrics
from .study_v11 import add_weather_features,compare_predeclared_corrections,with_predictions,safety_diagnostics,feature_matrix


def load_site(entry:dict):
    for key in ['station_id','site_id','latitude_deg','longitude_deg',
                'japan_json','weather_json','coordinate_status']:
        if key not in entry:raise ValueError(f'Falta {key} en manifiesto')
    if entry['coordinate_status'] not in ('exact_instrument_verified','site_proxy_not_instrument'):
        raise ValueError('coordinate_status inválido')
    jp=json.loads(Path(entry['japan_json']).read_text(encoding='utf-8'))
    met=json.loads(Path(entry['weather_json']).read_text(encoding='utf-8'))
    refs,_=normalize_observed(jp,station_no=int(entry['station_id']),site_id=entry['site_id'],
                              latitude_deg=float(entry['latitude_deg']),longitude_deg=float(entry['longitude_deg']))
    weather=normalize_openmeteo(met,session_id=entry['site_id'])
    pairs,_=pair_and_predict(refs,weather,model='ono')
    # El parser solo admite WBGT de origen parcial instrumental con calidad completa.
    return add_weather_features(pairs,weather)


def evaluate_manifest(entries:list[dict],*,min_days:int=6):
    if not entries:raise ValueError('No hay estaciones')
    ids=[str(x['site_id']) for x in entries]
    if len(ids)!=len(set(ids)):raise ValueError('site_id duplicado')
    stations=[]; sets={}
    for entry in entries:
        rows=load_site(entry)
        nd=len(set(r['jst_day'] for r in rows))
        sts='evaluated' if len(rows)>=48 and nd>=min_days else 'blocked_insufficient_days_or_rows'
        stations.append({'site_id':entry['site_id'],'station_id':entry['station_id'],
                         'coordinate_status':entry['coordinate_status'],'status':sts,
                         'n':len(rows),'days':nd,'metrics':errors_metrics(rows) if sts=='evaluated' else None})
        if sts=='evaluated':sets[entry['site_id']]=rows
    report={'research_only':True,'hardware_clip_validated':False,'sites':stations,
            'n_valid_sites':len(sets),'cross_site_generalization':{},
            'note':'Datos meteorológicos de reanálisis; referencia japonesa parcialmente instrumental; nunca certificación ISO.'}
    if len(sets)<3:
        report['cross_site_generalization']={'status':'blocked_need_3_or_more_sites',
             'available_site_ids':sorted(sets)}
        return report
    try:
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        from sklearn.linear_model import Ridge
    except ImportError:
        report['cross_site_generalization']={'status':'blocked_install_scikit_learn'};return report
    trials={}
    for heldout, test in sets.items():
        train=[r for sid,values in sets.items() if sid !=heldout for r in values]
        # Nunca mezclamos la estación de prueba en entrenamiento.
        model=make_pipeline(StandardScaler(),Ridge(alpha=10.0))
        model.fit(feature_matrix(train),[-float(x['error_c']) for x in train],
                  ridge__sample_weight=[3.0 if x['reference_c']>=28 else 1.0 for x in train])
        pred=model.predict(feature_matrix(test))
        corrected=with_predictions(test,[x['model_c']+y for x,y in zip(test,pred)])
        trials[heldout]={ 'train_sites':sorted(set(sets)-{heldout}),
                          'n_test':len(test),'baseline_metrics':errors_metrics(test),
                          'corrected_metrics':errors_metrics(corrected),
                          'research_false_low_original':safety_diagnostics(test)['false_low_count'],
                          'research_false_low_corrected':safety_diagnostics(corrected)['false_low_count']}
    report['cross_site_generalization']={'status':'exploratory_leave_one_site_out','fixed_model':'Ridge(alpha=10); weighted high=3; no grid-search','sites':trials}
    return report


def main():
    a=argparse.ArgumentParser(description='Validación multiestación, sin métricas inventadas')
    a.add_argument('--manifest',required=True);a.add_argument('--out',default='results/v11_multisitio.json')
    args=a.parse_args()
    entries=json.loads(Path(args.manifest).read_text(encoding='utf-8'))
    r=evaluate_manifest(entries);target=Path(args.out);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Guardado:',target)
    print('Estado generalización:',r['cross_site_generalization']['status'])

if __name__=='__main__':main()
