"""Reconstruir CSV estandarizado a partir de los dos ZIP originales v0.12 del usuario.

Uso: python scripts/build_historical_dataset_v20.py --first ruta_a_primer_zip --second ruta_a_segundo_zip
No descarga datos; verifica esquema y horas antes de escribir.
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import zipfile
import pandas as pd
import numpy as np


def build(first:Path,second:Path,out:Path):
    manifest=[]; parts=[]
    for archive in (first,second):
        manifest.append({'archive':archive.name,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()})
        with zipfile.ZipFile(archive) as z:
            observations=pd.read_csv(io.BytesIO(z.read('results/predicciones_horarias.csv')))
            observations['timestamp_utc']=pd.to_datetime(observations.timestamp_utc,utc=True)
            for site, part in observations.groupby('site_id'):
                raw=json.loads(z.read(f'sources/{site}/weather_raw.json'))
                hourly=raw['hourly']
                weather=pd.DataFrame({
                    'timestamp_utc':pd.to_datetime(hourly['time'],utc=True),
                    'temperature_c':hourly['temperature_2m'],
                    'relative_humidity_pct':hourly['relative_humidity_2m'],
                    'pressure_hpa':hourly['surface_pressure']})
                merged=part.merge(weather,on='timestamp_utc',validate='one_to_one',how='left')
                if merged[['temperature_c','relative_humidity_pct','pressure_hpa']].isna().any().any():
                    raise ValueError('Faltan datos de meteorología para '+site)
                parts.append(merged)
    df=pd.concat(parts,ignore_index=True).sort_values(['site_id','timestamp_utc'])
    if df.duplicated(['site_id','timestamp_utc']).any():raise ValueError('Horas duplicadas')
    if len(df)!=2976:raise ValueError(f'Se esperaban 2976 observaciones, recibidas {len(df)}')
    hour=(df.timestamp_utc.dt.hour+9)%24
    df['hour_sin']=np.sin(2*np.pi*hour/24)
    df['hour_cos']=np.cos(2*np.pi*hour/24)
    df['air_data_origin']='open_meteo_reanalysis'
    df['wbgt_reference_origin']='japan_moe_partial_instrumental'
    df['timestamp_utc']=df.timestamp_utc.dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    out.parent.mkdir(parents=True,exist_ok=True)
    df.to_csv(out,index=False,float_format='%.8f')
    (out.parent/'ORIGEN_Y_SHA256.json').write_text(json.dumps({'source_archives':manifest,'rows':len(df)},indent=2),encoding='utf-8')
    print(f'Archivo creado: {out} ({len(df)} registros)')

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--first',type=Path,required=True);a.add_argument('--second',type=Path,required=True)
    a.add_argument('--out',type=Path,default=Path('research_data/observaciones_japon_2025_agosto.csv'))
    arg=a.parse_args();build(arg.first,arg.second,arg.out)
