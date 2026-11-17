"""Diagnóstico no destructivo de la integración Liljegren (HeatGuard v0.11).

No modifica las bases, no reentrena modelos ni genera métricas de precisión.
Requiere solo los JSON ya descargados; puede funcionar aunque `lwbgt` falle.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import sys
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path

from .japan_api_v09 import normalize_observed
from .weather_history_v07 import normalize_openmeteo
from .liljegren import calculate_optional


DEMO_INPUT = dict(
    year=2024, month=4, day=15, hour=14, minute=30,
    gmt_offset_hours=8, averaging_minutes=60, urban=1,
    latitude_deg_north=1.3521, longitude_deg_east=103.8198,
    solar_w_m2=742.0, pressure_hpa=1008.4,
    air_temperature_c=32.1, relative_humidity_percent=68.0,
    wind_speed_m_s=2.8, wind_height_m=10.0,
    vertical_temperature_difference_c=1,
)


def diagnose(japan_path: Path, weather_path: Path, *, limit: int = 12) -> dict:
    out = {'status': 'diagnostic_only', 'python': sys.version.split()[0],
           'executable': sys.executable, 'lwbgt': {}, 'official_example': {},
           'data_rows': {}, 'samples': [], 'error_counts': {}}
    try:
        lib=importlib.import_module('lwbgt')
        out['lwbgt']['imported'] = True
        out['lwbgt']['path'] = getattr(lib,'__file__',None)
        try:
            out['lwbgt']['package_version'] = importlib.metadata.version('lwbgt')
        except importlib.metadata.PackageNotFoundError:
            out['lwbgt']['package_version'] = 'unknown'
        out['lwbgt']['has_Input'] = hasattr(lib,'Input')
        out['lwbgt']['has_calculate'] = hasattr(lib,'calculate')
        try:
            from lwbgt import Input, calculate
            result=calculate(Input(**DEMO_INPUT))
            out['official_example']={'status':int(result.status),
                                     'wbgt_c':float(result.wbgt_c) if result.status==0 else None}
        except Exception as exc:
            out['official_example']={'error_type':type(exc).__name__, 'error_message':str(exc)}
    except Exception as exc:
        out['lwbgt']={'imported':False,'error_type':type(exc).__name__, 'error_message':str(exc)}

    japan=json.loads(japan_path.read_text(encoding='utf-8-sig'))
    weather=json.loads(weather_path.read_text(encoding='utf-8-sig'))
    refs,qc=normalize_observed(japan, station_no=44132, site_id='JP_TOKYO',
                               latitude_deg=35.718547, longitude_deg=139.746464)
    met=normalize_openmeteo(weather, session_id='liljegren_v11_diagnostic')
    byts={x['timestamp_utc']:x for x in met}
    candidates=[(r,byts[r['timestamp_utc']]) for r in refs if r['timestamp_utc'] in byts]
    out['data_rows']={'references':len(refs),'weather':len(met), 'paired':len(candidates), 'quality':qc}
    if not candidates:
        out['status']='no_matching_rows'
        return out
    # Muestras distribuidas por radiación y horas, sin usar la referencia para decidir.
    daytime=[p for p in candidates if p[1]['solar_w_m2']>100]
    nighttime=[p for p in candidates if p[1]['solar_w_m2']<=20]
    seq=(daytime[:max(1,limit//2)] + nighttime[:max(1,limit//2)])[:limit]
    reasons=Counter()
    for ref, w in seq:
        vals={'air_temperature_c':float(w['air_temperature_c']),
              'relative_humidity_pct':float(w['relative_humidity_pct']),
              'solar_w_m2':float(w['solar_w_m2']),
              'wind_speed_m_s':float(w['wind_speed_10m_m_s']),
              'pressure_hpa':float(w['pressure_hpa'])}
        ctx={'environment':'outdoor',
             'location':{'latitude_deg':float(ref['latitude_deg']),
                         'longitude_deg':float(ref['longitude_deg']),
                         'utc_offset_hours':9},
             'weather_model':{'wind_height_m':10,'averaging_minutes':60,
                              'urban':1,'vertical_temperature_difference_c':0}}
        try:
            result=calculate_optional(vals,w['timestamp_utc'],ctx)
        except Exception as exc:
            result={'status':'uncaught_exception','error_type':type(exc).__name__, 'details':str(exc)}
        key=f"{result.get('status')} :: {result.get('details') or result.get('missing') or 'unspecified'}"
        reasons[key]+=1
        out['samples'].append({'timestamp_utc':w['timestamp_utc'],
                               'temperature_c':vals['air_temperature_c'],
                               'humidity_pct':vals['relative_humidity_pct'],
                               'solar_w_m2':vals['solar_w_m2'],
                               'wind_10m_m_s':vals['wind_speed_m_s'],
                               'result':result})
    out['error_counts']=dict(reasons)
    out['samples_tested']=len(seq)
    out['computed_count']=sum(x['result'].get('status')=='computed' for x in out['samples'])
    return out


def main():
    ap=argparse.ArgumentParser(description='Diagnóstico de errores Liljegren de HeatGuard v0.11')
    ap.add_argument('--japan-json',default='data/tokyo_2025_aug_user_run/japon_respuesta.json')
    ap.add_argument('--weather-json',default='data/tokyo_2025_aug_user_run/openmeteo_respuesta.json')
    ap.add_argument('--limit',type=int,default=12)
    ap.add_argument('--out',default='results/liljegren_diagnostico.json')
    a=ap.parse_args()
    if not (1 <= a.limit <= 336): ap.error('--limit debe estar entre 1 y 336')
    output=diagnose(Path(a.japan_json),Path(a.weather_json),limit=a.limit)
    dest=Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(output,indent=2,ensure_ascii=False),encoding='utf-8')
    print('Diagnóstico guardado:',dest)
    print('Biblioteca:',output.get('lwbgt'))
    print('Ejemplo oficial:',output.get('official_example'))
    print('Calculados:',output.get('computed_count',0),'de',output.get('samples_tested',0))
    print('Motivos:',json.dumps(output.get('error_counts',{}),ensure_ascii=False))

if __name__=='__main__':
    main()
