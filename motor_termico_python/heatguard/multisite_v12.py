"""HeatGuard v0.12: evaluación multiestación con datos observados, sin dispositivo.

Entrada: respuestas JSON originales de Japan MOE getSurveyData y Open-Meteo Historical.
Referencia: Tg observada + temperatura meteorológica + Tw calculada, NO ISO 7243.
Estudio exploratorio: estimación regional ≠ validación del clip en una faena.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import zipfile
from datetime import date, timedelta
from pathlib import Path, PurePosixPath, PureWindowsPath
from statistics import mean
from typing import Any

from .japan_api_v09 import build_url, fetch_json as fetch_japan, normalize_observed
from .weather_history_v07 import history_url, fetch_json as fetch_weather, normalize_openmeteo
from .independent_validation_v09 import pair_and_predict
from .benchmark_v10 import errors_metrics

RESEARCH_CUTOFF_C = 28.0
MODEL_NAMES = ('ono', 'liljegren')


def _portable_relative_path(value: object) -> bool:
    """Return True only for paths that are relative on Windows *and* POSIX.

    ``Path('/tmp/x').is_absolute()`` is false on Windows because it is parsed
    with Windows rules.  Configuration files are portable artifacts, so both
    path syntaxes must be rejected along with parent-directory traversal.
    """
    raw = str(value)
    posix = PurePosixPath(raw)
    windows = PureWindowsPath(raw)
    return not (posix.is_absolute() or windows.is_absolute() or '..' in posix.parts
                or '..' in windows.parts)


def load_config(filename: Path, *, root: Path | None = None) -> tuple[dict, Path]:
    """Resuelve rutas relativas con la carpeta raíz del proyecto, no con el cwd accidental."""
    conf = json.loads(filename.read_text(encoding='utf-8'))
    root = root if root is not None else filename.resolve().parent.parent
    if not isinstance(conf.get('stations'), list) or not conf['stations']:
        raise ValueError('stations debe ser una lista no vacía')
    if date.fromisoformat(conf['date_start']) > date.fromisoformat(conf['date_end']):
        raise ValueError('date_start posterior a date_end')
    ids = set(); sites = set()
    for s in conf['stations']:
        for k in ('station_id','site_id','latitude_deg','longitude_deg','coordinate_status','japan_json','weather_json'):
            if k not in s: raise ValueError(f'Estación sin campo {k}')
        if int(s['station_id']) in ids or str(s['site_id']) in sites:
            raise ValueError('No repetir station_id ni site_id (falsa validación multiestación)')
        ids.add(int(s['station_id'])); sites.add(str(s['site_id']))
        if not (-90 <= float(s['latitude_deg']) <= 90 and -180 <= float(s['longitude_deg']) <= 180):
            raise ValueError('Coordenadas inválidas')
        if not _portable_relative_path(s['japan_json']) or not _portable_relative_path(s['weather_json']):
            raise ValueError('Usar rutas relativas para portabilidad')
    return conf, root


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_info(path: Path) -> dict:
    payload=path.read_bytes()
    return {'path':str(path),'sha256':sha256_bytes(payload),'bytes':len(payload)}


def download_missing(conf: dict, root: Path, *, overwrite: bool = False) -> list[dict]:
    """Descarga SOLO al invocar --download; no sustituye datos cacheados silenciosamente."""
    audit=[]
    for site in conf['stations']:
        ref=root/site['japan_json']; met=root/site['weather_json']
        first,last=conf['date_start'],conf['date_end']
        requests=[('japan',ref, build_url(site['station_id'],first,last), fetch_japan),
                  ('weather',met, history_url(site['latitude_deg'],site['longitude_deg'],
                                               (date.fromisoformat(first)-timedelta(days=1)).isoformat(),
                                               (date.fromisoformat(last)+timedelta(days=1)).isoformat()), fetch_weather)]
        for kind,path,url,fn in requests:
            if path.exists() and not overwrite:
                audit.append({'station':site['site_id'],'type':kind,'status':'already_cached','path':str(path)})
                continue
            try:
                obj=fn(url)
                if kind=='japan':
                    if not isinstance(obj.get('data'),list): raise ValueError('Japan: no hay lista de observaciones')
                else:
                    if not isinstance(obj.get('hourly'),dict): raise ValueError('Open-Meteo: sin bloque hourly')
                path.parent.mkdir(parents=True,exist_ok=True)
                tmp=path.with_name(path.name+'.part')
                tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
                tmp.replace(path)
                audit.append({'station':site['site_id'],'type':kind,'status':'downloaded','path':str(path)})
            except Exception as exc:
                audit.append({'station':site['site_id'],'type':kind,'status':'download_failed',
                              'error':f'{type(exc).__name__}: {exc}'})
    return audit


def load_raw(site:dict,root:Path) -> tuple[dict,dict,dict]:
    paths=[root/site['japan_json'],root/site['weather_json']]
    missing=[str(p) for p in paths if not p.exists()]
    if missing: raise FileNotFoundError('Faltan descargas: '+', '.join(missing))
    return json.loads(paths[0].read_text(encoding='utf-8')), json.loads(paths[1].read_text(encoding='utf-8')), \
           {'reference':file_info(paths[0]),'weather':file_info(paths[1])}


def paired_models(references:list[dict], weather:list[dict], *, optional_liljegren=True):
    """Intersección estricta: misma fecha y misma referencia para cada modelo."""
    by_model={}; rejects={}; availability={}
    for name in MODEL_NAMES:
        if name=='liljegren':
            try: import lwbgt  # noqa: F401
            except ImportError:
                availability[name]='dependency_unavailable_lwbgt'; continue
        rows,rej=pair_and_predict(references,weather,model=name)
        by_model[name]={r['timestamp_utc']:r for r in rows}
        rejects[name]=rej
        availability[name]='evaluated' if rows else 'no_valid_predictions'
    if 'ono' not in by_model or not by_model['ono']:
        raise ValueError('No se obtuvieron pares válidos del modelo Ono')
    common=set(by_model['ono'])
    if 'liljegren' in by_model and by_model['liljegren']:
        common &= set(by_model['liljegren'])
    common=sorted(common)
    output=[]
    for ts in common:
        ono=by_model['ono'][ts]
        row={'site_id':ono['site_id'],'timestamp_utc':ts,'jst_day':ono['jst_day'],
             'reference_c':float(ono['reference_c']), 'ono_c':float(ono['model_c']),
             'solar_w_m2':float(ono['solar_w_m2']),
             'wind_10m_m_s':float(ono['wind_speed_10m_m_s']),
             'distance_km':float(ono['distance_km']),
             'reference_quality_code':4}
        if ts in by_model.get('liljegren',{}):
            lj=by_model['liljegren'][ts]
            if abs(float(lj['reference_c'])-row['reference_c'])>1e-9:
                raise ValueError('Referencias inconsistentes a una misma hora')
            row['liljegren_c']=float(lj['model_c'])
        output.append(row)
    return output,{'model_status':availability,'rejected':rejects,
                    'n_ono_only':len(set(by_model['ono'])-set(by_model.get('liljegren',{}))) if 'liljegren' in by_model else None,
                    'n_common':len(common)}


def model_metrics(rows:list[dict],model:str,cutoff:float=RESEARCH_CUTOFF_C) -> dict|None:
    if not rows or any(model+'_c' not in r for r in rows): return None
    refs=[float(x['reference_c']) for x in rows]
    vals=[float(x[model+'_c']) for x in rows]
    err=[m-r for m,r in zip(vals,refs)]
    high=[(r,m,e) for r,m,e in zip(refs,vals,err) if r>=cutoff]
    low=[(r,m,e) for r,m,e in zip(refs,vals,err) if r<cutoff]
    out=errors_metrics([{'error_c':e} for e in err])
    out.update({
        'high_reference_n':len(high),
        'false_low_count':sum(m<cutoff for _,m,_ in high),
        'false_low_pct_given_high':round(100*sum(m<cutoff for _,m,_ in high)/len(high),2) if high else None,
        'false_high_count':sum(m>=cutoff for _,m,_ in low),
        'false_high_pct_given_low':round(100*sum(m>=cutoff for _,m,_ in low)/len(low),2) if low else None,
        'high_mae_c':round(mean(abs(e) for _,_,e in high),4) if high else None,
        'high_bias_c':round(mean(e for _,_,e in high),4) if high else None,
        'high_under_gt_1_count':sum(e<-1 for _,_,e in high),
    })
    return out


def grouped_metrics(rows:list[dict],model:str,cutoff:float) -> dict:
    return {
        'all':model_metrics(rows,model,cutoff),
        'day_ghi_gt_20':model_metrics([r for r in rows if r['solar_w_m2']>20],model,cutoff),
        'low_ghi_le_20':model_metrics([r for r in rows if r['solar_w_m2']<=20],model,cutoff),
        'high_reference':model_metrics([r for r in rows if r['reference_c']>=cutoff],model,cutoff),
    }


def bootstrap_paired_mae_delta(rows:list[dict],*,replicates:int=1000,seed:int=42) -> dict:
    if not rows or any('liljegren_c' not in r for r in rows):
        return {'status':'unavailable_requires_paired_liljegren'}
    groups={}
    for r in rows:groups.setdefault((r['site_id'],r['jst_day']),[]).append(r)
    blocks=list(groups.values())
    if len(blocks)<6:return {'status':'insufficient_days'}
    rng=random.Random(seed);deltas=[]
    for _ in range(replicates):
        sample=[r for _ in blocks for r in blocks[rng.randrange(len(blocks))]]
        delta=mean(abs(r['liljegren_c']-r['reference_c'])-abs(r['ono_c']-r['reference_c']) for r in sample)
        deltas.append(delta)
    deltas.sort()
    return {'status':'exploratory_block_bootstrap','days':len(blocks),'replicates':replicates,
            'mae_liljegren_minus_ono_ci95_c':[round(deltas[int(replicates*.025)],4),round(deltas[int(replicates*.975)-1],4)],
            'interpretation':'Un intervalo en días/sitios observados; no valida faenas chilenas.'}


def leave_one_site_out_bias(site_rows:dict[str,list[dict]],model:str,cutoff:float) -> dict:
    """Ajusta un único sesgo con OTROS sitios; prueba en sitio jamás usado."""
    if len(site_rows)<3:return {'status':'blocked_need_3_or_more_distinct_valid_sites'}
    trials={}
    for site,test in site_rows.items():
        if any(model+'_c' not in r for r in test):return {'status':'model_unavailable_on_some_sites'}
        training=[r for sid,block in site_rows.items() if sid!=site for r in block]
        fitted=mean(x[model+'_c']-x['reference_c'] for x in training)
        pred=[{**r,model+'_c':r[model+'_c']-fitted} for r in test]
        trials[site]={'train_sites':sorted(set(site_rows)-{site}), 'n_test':len(test),
                      'train_only_bias_c':round(fitted,4),
                      'baseline':model_metrics(test,model,cutoff),
                      'bias_corrected':model_metrics(pred,model,cutoff)}
    return {'status':'research_leave_one_site_out','method':'train-only global bias, no hyperparameter tuning',
            'trials':trials,'not_deployable':True}


def score_site(site:dict,root:Path, *,cutoff:float, min_days:int,min_pairs:int):
    entry={'site_id':site['site_id'],'station_id':int(site['station_id']),
           'name':site.get('name',site['site_id']),
           'latitude_deg':float(site['latitude_deg']),'longitude_deg':float(site['longitude_deg']),
           'coordinate_status':site['coordinate_status'],'status':'pending'}
    try:
        j,met,files=load_raw(site,root)
        refs,q=normalize_observed(j,station_no=int(site['station_id']),site_id=site['site_id'],
                                  latitude_deg=site['latitude_deg'],longitude_deg=site['longitude_deg'])
        wx=normalize_openmeteo(met,session_id=site['site_id'])
        entry.update({'file_manifest':files,'reference_filter_counts':q,'weather_hour_count':len(wx)})
        if not refs: raise ValueError('Sin registros Japan class=1 y WI=4; verificar que la estación sea instrumental')
        rows,checks=paired_models(refs,wx)
        if len(rows)<min_pairs or len({r['jst_day'] for r in rows})<min_days:
            entry.update({'status':'blocked_insufficient_paired_data','paired':checks,'pairs':len(rows)})
            return entry,[]
        entry.update({'status':'evaluated' if checks['model_status'].get('liljegren')=='evaluated' else 'partial_only_ono',
                      'n_pairs':len(rows),'n_days':len({r['jst_day'] for r in rows}),
                      'pairing':checks,'metrics':{m:grouped_metrics(rows,m,cutoff) for m in MODEL_NAMES if m+'_c' in rows[0]},
                      'paired_bootstrap':bootstrap_paired_mae_delta(rows)})
        return entry,rows
    except (FileNotFoundError,ValueError,KeyError,TypeError) as exc:
        entry['status']='blocked_missing_or_invalid_source';entry['reason']=f'{type(exc).__name__}: {exc}'
        return entry,[]


def evaluate(conf:dict,root:Path):
    cutoff=float(conf.get('threshold_research_only_c',28))
    min_days=int(conf.get('min_valid_days',6));min_pairs=int(conf.get('min_pairs_per_site',48))
    entries=[]; allrows=[];site_rows={}
    digests={}
    for s in conf['stations']:
        info,rows=score_site(s,root,cutoff=cutoff,min_days=min_days,min_pairs=min_pairs)
        # Detect copy-pasted raw source masquerading as a distinct site.
        signature=info.get('file_manifest',{}).get('reference',{}).get('sha256')
        if signature and signature in digests:
            info={'site_id':s['site_id'],'station_id':s['station_id'],'status':'blocked_duplicate_reference_bytes',
                  'reason':f'Referencia binariamente idéntica a {digests[signature]}'}; rows=[]
        elif signature:digests[signature]=s['site_id']
        entries.append(info)
        if rows:
            allrows.extend(rows);site_rows[s['site_id']]=rows
    # Availability: no Liljegren -> show Ono only, no invented comparison.
    full_rows=[r for r in allrows if 'liljegren_c' in r]
    pooled={}
    for model in MODEL_NAMES:
        sub=[r for r in allrows if model+'_c' in r]
        pooled[model]={'n':len(sub),'metrics':grouped_metrics(sub,model,cutoff) if sub else None}
    cross_site={model:leave_one_site_out_bias({sid:rs for sid,rs in site_rows.items() if all(model+'_c' in r for r in rs)},model,cutoff)
                for model in MODEL_NAMES}
    macro={}
    for model in MODEL_NAMES:
        available=[(s.get('metrics') or {}).get(model,{}).get('all') for s in entries]
        available=[m for m in available if m]
        macro[model]={'n_sites':len(available),'mean_site_mae_c':round(mean(m['mae_c'] for m in available),4) if available else None}
    return {'status':'observational_software_validation_exploratory',
            'study_id':conf.get('study_id'),'period':[conf['date_start'],conf['date_end']],
            'research_cutoff_not_occupational_threshold_c':cutoff,'sites':entries,
            'valid_sites':len(site_rows),'n_rows_total':len(allrows),
            'n_strictly_paired_both_models':len(full_rows),
            'pooled':pooled,'macro_average_by_site':macro,'paired_comparison_bootstrap':bootstrap_paired_mae_delta(full_rows),
            'leave_one_site_out':cross_site,
            'kong_huber':{'status':'not_evaluated','reason':'Requiere flujos radiativos de onda larga/corta ascendentes y descendentes, coseno cenital y fracción directa; no completarlos con supuestos ocultos. Código fuente de autores licenciado GPL-3.0: uso comercial requiere revisión.'},
            'limitations':[
                'Referencia Japón MOE: globo observado + Tw psicrométrico calculado; no es medición ISO 7243 completa.',
                'Open-Meteo: meteorología regional reanalizada; viento 10 m y radiación promediada por hora.',
                'Coordenadas de estaciones son aproximaciones (ver coordinate_status), no ubicaciones exactas verificadas.',
                'El corte de 28 C es exploratorio, NO determina seguridad ocupacional.',
                'Tokio fue explorado antes; no usarlo como test virgen para elegir hiperparámetros.',
                'No hay validación de sensores, montaje, trabajador o alertas clínicas/ocupacionales del clip.',
            ]},allrows


def save_report(report:dict,rows:list[dict],folder:Path):
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'reporte_multisitio_v12.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    cols=['site_id','timestamp_utc','jst_day','reference_c','ono_c','liljegren_c','solar_w_m2','wind_10m_m_s','distance_km','reference_quality_code']
    with (folder/'predicciones_horarias.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore');w.writeheader();w.writerows(rows)
    lines=['# HeatGuard v0.12 — Benchmark observacional multiestación','',
           f"**Estaciones con datos admisibles:** {report['valid_sites']} de {len(report['sites'])}.",
           f"**Pares:** {report['n_rows_total']}; **pareados Ono–Liljegren:** {report['n_strictly_paired_both_models']}.",'',
           '| Sitio | Estado | n | MAE Ono | MAE Liljegren | Falsos bajos Ono | Falsos bajos Liljegren |',
           '|---|---|---:|---:|---:|---:|---:|']
    for x in report['sites']:
        mt=x.get('metrics',{});a=(mt.get('ono') or {}).get('all') or {};b=(mt.get('liljegren') or {}).get('all') or {}
        def fmt(v):return '—' if v is None else str(v)
        lines.append(f"| {x['site_id']} | {x['status']} | {x.get('n_pairs','—')} | {fmt(a.get('mae_c'))} | {fmt(b.get('mae_c'))} | {fmt(a.get('false_low_count'))} | {fmt(b.get('false_low_count'))} |")
    lines+=['','## Generalización entre estaciones']
    for model,cv in report['leave_one_site_out'].items():lines.append(f'- {model}: **{cv["status"]}**')
    lines+=['','## Limitaciones']+[f'- {v}' for v in report['limitations']]
    lines+=['','## Kong–Huber',report['kong_huber']['reason']]
    (folder/'INFORME_MULTISITIO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    try:
        import matplotlib.pyplot as plt
        usable=[s for s in report['sites'] if (s.get('metrics') or {}).get('ono')]
        if usable:
            fig,ax=plt.subplots(figsize=(9,4.4));x=list(range(len(usable)))
            a=[s['metrics']['ono']['all']['mae_c'] for s in usable]
            ax.bar([j-0.2 for j in x],a,width=.4,label='Ono')
            has_l=any('liljegren' in s['metrics'] for s in usable)
            if has_l:
                vals=[s['metrics'].get('liljegren',{}).get('all',{}).get('mae_c',float('nan')) for s in usable]
                ax.bar([j+0.2 for j in x],vals,width=.4,label='Liljegren')
            ax.set_xticks(x,[s['site_id'] for s in usable]);ax.set_ylabel('MAE vs referencia (°C)');ax.set_title('Comparación exploratoria por estación');ax.legend();fig.tight_layout()
            fig.savefig(folder/'comparacion_mae.png',dpi=140);plt.close(fig)
    except ImportError:pass


def make_bundle(folder:Path,root:Path,conf:dict,output:Path):
    """Paquete para auditoría: resultados y fuentes JSON originales (solo datos públicos)."""
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=7) as archive:
        archive.writestr('config/multisite_2025_08_v12.json',json.dumps(conf,ensure_ascii=False,indent=2))
        for p in sorted(folder.iterdir()):
            if p.is_file():archive.write(p,'results/'+p.name)
        for station in conf['stations']:
            for kind,k in [('japan','japan_json'),('weather','weather_json')]:
                src=root/station[k]
                if src.is_file():archive.write(src,'sources/'+station['site_id']+'/'+kind+'_raw.json')
    return output


def main(argv:list[str]|None=None):
    p=argparse.ArgumentParser(description='HeatGuard: validación observacional multiestación, sin hardware')
    p.add_argument('--config',type=Path,default=Path('config/multisite_2025_08_v12.json'))
    p.add_argument('--root',type=Path,default=Path('.'))
    p.add_argument('--out',type=Path,default=Path('results/multisite_v12'))
    p.add_argument('--download',action='store_true',help='Autoriza descarga explícita Japan MOE y Open-Meteo de archivos faltantes')
    p.add_argument('--overwrite',action='store_true',help='Con --download, vuelve a solicitar incluso archivos cacheados')
    p.add_argument('--bundle',type=Path,help='Crea un ZIP para revisión con informe y fuentes originales (datos públicos)')
    args=p.parse_args(argv)
    config,root=load_config(args.config,root=args.root)
    audits=[]
    if args.download:audits=download_missing(config,root,overwrite=args.overwrite)
    report,rows=evaluate(config,root)
    report['download_audit']=audits
    save_report(report,rows,args.out)
    if args.bundle:
        make_bundle(args.out,root,config,args.bundle)
        print('ZIP de auditoría:',args.bundle.resolve())
    print(f"Estaciones válidas: {report['valid_sites']}/{len(report['sites'])}; registros: {report['n_rows_total']}; pareados: {report['n_strictly_paired_both_models']}")
    for s in report['sites']:print(f"  {s['site_id']}: {s['status']} {s.get('n_pairs','')} {s.get('reason','')}")
    print('Resultados en',args.out.resolve())
    return report

if __name__=='__main__':main()
