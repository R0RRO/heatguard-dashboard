"""Reproducción histórica de Ono con fuentes JMA/meteorología regional.

NO es telemetría de un HeatGuard Clip. La referencia comparte entradas
JMA con el modelo: resultado es concordancia observacional parcial.
"""
from __future__ import annotations
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from heatguard.pipeline import evaluate

ROOT = Path(__file__).resolve().parent.parent
FUKUOKA = ROOT / 'research_validation' / 'fukuoka_regional_reference_744h.csv'
JMA = ROOT / 'research_validation' / 'fukuoka_jma_hourly_744h.csv'
PARAMS = {'air_temperature_c':'degC', 'relative_humidity_pct':'percent',
          'solar_w_m2':'W/m2','wind_speed_m_s':'m/s','pressure_hpa':'hPa'}


def run() -> dict:
    with JMA.open(encoding='utf-8-sig', newline='') as f:
        local = {datetime.fromisoformat(x['timestamp_jst']).astimezone(timezone.utc).isoformat(): x
                 for x in csv.DictReader(f)}
    rows = []
    with FUKUOKA.open(encoding='utf-8-sig', newline='') as f:
        for line in csv.DictReader(f):
            if line['site_id'] != 'JP_FUKUOKA':
                continue
            ts = datetime.fromisoformat(line['timestamp_utc'].replace('Z','+00:00')).isoformat()
            j = local.get(ts)
            if j is None:
                raise RuntimeError(f'JMA sin hora {ts}')
            values = {'air_temperature_c':float(j['temperature_c']),
                      'relative_humidity_pct':float(j['humidity_pct']),
                      'solar_w_m2':float(line['shortwave_radiation']),
                      'wind_speed_m_s':float(line['wind_speed_10m']),
                      'pressure_hpa':float(j['station_pressure_hpa'])}
            readings = [{'parameter':name,'value':value,'unit':PARAMS[name],
                         'kind':'external','source':('JMA_OBSERVATION_47807' if name in
                          ('air_temperature_c','relative_humidity_pct','pressure_hpa')
                          else 'OPEN_METEO_HISTORICAL_REANALYSIS'),
                         'timestamp':ts} for name,value in values.items()]
            event = {'device_id':'JMA-47807-RESEARCH-NOT-A-CLIP','timestamp':ts,
                     'context':{'zone_id':'FUKUOKA-STATION','environment':'outdoor'},
                     'observations':readings}
            result=evaluate(event)['environmental_estimator_v18']
            if result['status']!='computed':
                raise RuntimeError(f'Bloqueo {ts}: {result}')
            rows.append((float(line['reference_c']), result['value_c']))
    if len(rows)!=744:
        raise RuntimeError('Se necesitan exactamente 744 pares de referencia JMA')
    errors=[pred-ref for ref,pred in rows]
    return {'source':'JMA local T/RH/P + Open-Meteo regional solar/wind; reference Japan MOE',
            'kind':'historical_research_not_clip', 'pairs':len(rows),
            'mae_c':round(mean(abs(x) for x in errors),4),
            'bias_c':round(mean(errors),4),
            'note':'Comparación parcialmente circular: JMA T/RH compartidas con referencia. No valida ISO/clip.'}


if __name__=='__main__':
    print(json.dumps(run(),ensure_ascii=False,indent=2))
