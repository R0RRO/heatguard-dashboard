"""Evaluación del modelo de WBGT exterior contra referencia japonesa con globo medido.

Comandos:
  python -m heatguard.independent_validation_v09 --station 44132 --lat 35.69 --lon 139.76 \\
      --start 2025-08-01 --end 2025-08-10 --download --model ono

Sin internet local: pasar --japan-json y --weather-json a archivos YA descargados.
Nunca publica métricas si faltan datos, no se alcanza el mínimo de pares o la
referencia es simulada. No contiene datos de referencia inventados.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
from statistics import mean

from .japan_api_v09 import build_url, fetch_json as fetch_japan, normalize_observed, sha256_json, save_raw, ts_to_jst_day
from .weather_history_v07 import history_url, fetch_json as fetch_weather, normalize_openmeteo
from .ono_v09 import wbgt_ono
from .liljegren import calculate_optional
from .reference_v07 import _metrics, _haversine_km


def pair_and_predict(references: list[dict], weather: list[dict], *, model: str = 'ono',
                     max_km: float = 20.0, urban: int = 1) -> tuple[list[dict], dict]:
    if model not in ('ono', 'liljegren'): raise ValueError('Modelo debe ser ono o liljegren')
    if not 0 < max_km <= 100: raise ValueError('max_km inválido')
    by_ts = {r['timestamp_utc']:r for r in weather}
    if len(by_ts) != len(weather): raise ValueError('Meteorología contiene horas duplicadas')
    pairs = []
    reject = {'no_matching_weather': 0, 'too_far': 0, 'model_failed': 0, 'other_origin': 0}
    for ref in references:
        if ref.get('source') != 'https://www.wbgt.env.go.jp/api/v1/getSurveyData' or int(ref.get('quality_code', -1)) != 4:
            reject['other_origin'] += 1; continue
        met = by_ts.get(ref['timestamp_utc'])
        if met is None:
            reject['no_matching_weather'] += 1; continue
        if met.get('data_origin') != 'reanalysis_model':
            reject['other_origin'] += 1; continue
        distance = _haversine_km(float(ref['latitude_deg']), float(ref['longitude_deg']),
                                 float(met['latitude_deg']), float(met['longitude_deg']))
        if distance > max_km:
            reject['too_far'] += 1; continue
        try:
            if model == 'ono':
                estimate = wbgt_ono(met['air_temperature_c'], met['relative_humidity_pct'],
                                    met['solar_w_m2'], met['wind_speed_10m_m_s'])
            else:
                result = calculate_optional({
                    'air_temperature_c': float(met['air_temperature_c']),
                    'relative_humidity_pct': float(met['relative_humidity_pct']),
                    'solar_w_m2': float(met['solar_w_m2']),
                    'wind_speed_m_s': float(met['wind_speed_10m_m_s']),
                    'pressure_hpa': float(met['pressure_hpa']),
                }, met['timestamp_utc'], {
                    'environment': 'outdoor',
                    'location': {'latitude_deg': float(ref['latitude_deg']),
                                 'longitude_deg': float(ref['longitude_deg']), 'utc_offset_hours': 9},
                    'weather_model': {'wind_height_m': 10, 'averaging_minutes': 60,
                                     'urban': urban, 'vertical_temperature_difference_c': 0.0},
                })
                if result.get('status') != 'computed':
                    raise RuntimeError(f'Liljegren no se calculó: {result}')
                estimate = float(result['value_c'])
        except (ValueError, RuntimeError, ArithmeticError):
            reject['model_failed'] += 1; continue
        if not math.isfinite(estimate):
            reject['model_failed'] += 1; continue
        pairs.append({
            'timestamp_utc': ref['timestamp_utc'], 'jst_day': ts_to_jst_day(ref['timestamp_utc']),
            'site_id': ref['site_id'], 'reference_c': ref['wbgt_reference_c'],
            'model_c': round(estimate, 5), 'error_c': round(estimate - ref['wbgt_reference_c'], 5),
            'solar_w_m2': met['solar_w_m2'], 'wind_speed_10m_m_s': met['wind_speed_10m_m_s'],
            'distance_km': round(distance, 3), 'quality_code': 4,
            'meteo_origin': 'Open-Meteo historical reanalysis', 'reference_origin': 'Japan MOE measured globe / computed psychrometric Tw',
        })
    pairs.sort(key=lambda p:p['timestamp_utc'])
    return pairs, reject


def stratified_metrics(pairs: list[dict]) -> dict:
    if not pairs: raise ValueError('Sin pares válidos')
    subsets = {
        'all': pairs,
        'day_ghi_gt_20': [r for r in pairs if r['solar_w_m2'] > 20],
        'night_ghi_le_20': [r for r in pairs if r['solar_w_m2'] <= 20],
        'reference_wbgt_ge_28': [r for r in pairs if r['reference_c'] >= 28],
    }
    out = {}
    for key, data in subsets.items():
        if not data:
            out[key] = None; continue
        out[key] = {**_metrics(data), 'underestimation_frequency': round(sum(r['error_c'] < 0 for r in data)/len(data), 4),
                    'p90_underestimation_c': round(sorted([max(0., -r['error_c']) for r in data])[math.ceil(.9*len(data))-1], 4)}
    return out


def temporal_holdout_jst(pairs: list[dict], *, fraction: float = .7) -> dict:
    dates = sorted({p['jst_day'] for p in pairs})
    if len(dates) < 6:
        return {'status': 'insufficient_days', 'n_days': len(dates), 'note':'Se exigen al menos 6 días independientes de Japón'}
    split = min(len(dates)-2, max(3, int(len(dates)*fraction)))
    training, evaluation = set(dates[:split]), set(dates[split:])
    train = [p for p in pairs if p['jst_day'] in training]
    test = [p for p in pairs if p['jst_day'] in evaluation]
    if len(train)<24 or len(test)<12:
        return {'status':'insufficient_pairs', 'n_train':len(train), 'n_test':len(test)}
    bias = mean([p['error_c'] for p in train]); corrected = [{**p, 'error_c':p['error_c']-bias} for p in test]
    return {'status':'evaluated', 'train_days_jst': sorted(training), 'test_days_jst': sorted(evaluation),
            'n_train':len(train), 'n_test':len(test), 'trained_bias_c':round(bias,4),
            'test_original': _metrics(test), 'test_corrected':_metrics(corrected),
            'note':'Corrección de sesgo aprendida solo de días anteriores; no se garantiza transportabilidad a otras estaciones'}


def run_reference_study(japan_obj:dict, weather_obj:dict, *, station:int, site_id:str,
                        latitude:float, longitude:float, model:str, max_km:float =20.0,
                        provenance_verified: bool = False) -> tuple[dict, list[dict], list[dict], list[dict]]:
    refs, quality = normalize_observed(japan_obj, station_no=station, site_id=site_id,
                                       latitude_deg=latitude, longitude_deg=longitude)
    weather = normalize_openmeteo(weather_obj, session_id=f'JP_MOE_{station}')
    if not refs:
        raise ValueError(f'La API japonesa no contiene referencias instrumentales con WI=4. Conteos: {quality}')
    pairs, rejected = pair_and_predict(refs, weather, model=model, max_km=max_km)
    if len(pairs) < 24:
        raise ValueError(f'Menos de 24 pares válidos: {len(pairs)}; rechazos={rejected}. No se emiten métricas')
    metrics = stratified_metrics(pairs)
    holdout = temporal_holdout_jst(pairs)
    report = {
        'research_only': True, 'comparison':f'{model} vs Japan MOE station globe-measured-computed-wetbulb',
        'instrument_reference_is_full_ISO7243': False, 'heatguard_clip_validated': False,
        'official_sources_downloaded_by_tool_in_this_run': bool(provenance_verified),
        'offline_import_provenance_unverified': not bool(provenance_verified),
        'japan_api': 'https://www.wbgt.env.go.jp/api/v1/getSurveyData',
        'japan_data_sha256_canonical_json':sha256_json(japan_obj),
        'weather_api':'https://archive-api.open-meteo.com/v1/archive',
        'weather_data_sha256_canonical_json':sha256_json(weather_obj),
        'model':model, 'station_no':station, 'site_id':site_id, 'station_coordinates_supplied_by_operator':[latitude,longitude],
        'quality_filter':{'wbgt_class':1,'wbgt_WI':4,'source_method':'Tg 6-inch observed, Ta measured, Tw psychrometric modeled'},
        'quality_counts':quality, 'discarded':rejected,
        'n_pairs':len(pairs), 'distance_km_max_allowed':max_km,
        'grid_distance_km_observed_max':max(p['distance_km'] for p in pairs),
        'metrics':metrics, 'temporal_holdout':holdout,
        'warnings':[
            'Open-Meteo is regional reanalysis, not station-colocated meteorology.',
            'Japan MOE measured series uses observed globe, but estimated psychrometric wet bulb under forced ventilation; not identical to natural wet bulb per ISO 7243.',
            'Open-Meteo shortwave_radiation is previous-hour mean; other variables are instantaneous. Hourly point matching cannot eliminate temporal representativeness error.',
            'Quality WI=4 does not certify a specific ISO 7243 deployment or calibration of HeatGuard.',
            'Never train on evaluation days. These metrics do not establish safety or a validated individual wearable.',
            'Offline imported JSON can be manipulated; hashes verify data identity, not external authenticity.',
        ],
    }
    return report, pairs, refs, weather


def save_outputs(dest: str | Path, report: dict, pairs:list[dict], refs:list[dict], weather:list[dict]) -> None:
    from .reference_v07 import REF_COLUMNS
    from .weather_history_v07 import CSV_COLUMNS
    dest = Path(dest); dest.mkdir(parents=True, exist_ok=True)
    (dest/'report_v09.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for filename, rows, columns in (
         ('matched_pairs.csv',pairs, list(pairs[0]) if pairs else []),
         ('reference_instrumental_filter_wi4.csv',refs, list(refs[0]) if refs else []),
         ('weather_reanalysis.csv',weather, list(weather[0]) if weather else [])):
        if not rows: continue
        with (dest/filename).open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
            writer.writeheader(); writer.writerows(rows)
    lines = [
        '# HeatGuard v0.9 — Primer contraste observacional', '',
        f"Modelo: **{report['model']}**; estación japonesa: **{report['station_no']}**; registros emparejados: **{report['n_pairs']}**.",
        '**Son resultados exploratorios con meteorología regional y referencia instrumental parcial, no validación de un clip ISO.**',
        '', '| Grupo | n | MAE (°C) | RMSE (°C) | Sesgo modelo−referencia (°C) |',
        '|---|---:|---:|---:|---:|',
    ]
    for k, v in report['metrics'].items():
        if v: lines.append(f"| {k} | {v['n']} | {v['mae_c']} | {v['rmse_c']} | {v['bias_model_minus_measured_c']} |")
    lines += ['', '## Temporal holdout', f"Estado: {report['temporal_holdout']['status']}", '', '## Advertencias']
    lines += [f'- {s}' for s in report['warnings']]
    (dest/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        xx = [datetime.fromisoformat(p['timestamp_utc'].replace('Z','+00:00')) for p in pairs]
        fig, ax = plt.subplots(figsize=(11,4.5))
        ax.plot(xx, [p['reference_c'] for p in pairs], label='Japón MOE: globo observado + Tw estimado')
        ax.plot(xx, [p['model_c'] for p in pairs], label=f'Modelo {report["model"]} con meteorología regional', alpha=.8)
        ax.set_ylabel('WBGT (°C)'); ax.set_title('Contraste observacional (NO validación HeatGuard)')
        ax.legend(fontsize=8); fig.autofmt_xdate();fig.tight_layout()
        fig.savefig(dest/'timeseries.png', dpi=150); plt.close(fig)
    except ImportError: pass


def main() -> None:
    p=argparse.ArgumentParser(description='Validación exploratoria WBGT Japón con WI=4 y reanálisis Open-Meteo')
    p.add_argument('--station',type=int,default=44132,help='Código estación; 44132 Tokyo (verificar coordenadas oficiales)')
    p.add_argument('--site-id', default='JP_TOKYO')
    p.add_argument('--lat',type=float,required=True,help='Coordenada verificada de la estación, no del celular')
    p.add_argument('--lon',type=float,required=True)
    p.add_argument('--start',required=True,help='YYYY-MM-DD JST')
    p.add_argument('--end',required=True)
    p.add_argument('--model',choices=['ono','liljegren'],default='ono')
    p.add_argument('--download',action='store_true',help='Obtener 2 JSON oficiales del internet')
    p.add_argument('--japan-json',help='Usar JSON descargado previamente, sin internet')
    p.add_argument('--weather-json',help='Usar JSON Open-Meteo descargado previamente, sin internet')
    p.add_argument('--max-distance-km',type=float,default=20)
    p.add_argument('--out',default='results/observational_v09')
    a=p.parse_args()
    if a.download and (a.japan_json or a.weather_json):
        p.error('Seleccionar --download o ambos archivos locales, no mezclar')
    if not a.download and not (a.japan_json and a.weather_json):
        p.error('Indicar --download o --japan-json y --weather-json')
    first, last = date.fromisoformat(a.start), date.fromisoformat(a.end)
    if (last-first).days > 31 or first>last:
        p.error('Se requiere una ventana máxima de 32 días')
    if a.model == 'liljegren':
        try:
            import lwbgt  # noqa: F401
        except ImportError as e:
            p.error('Falta lwbgt para --model liljegren. Ejecuta pip install -e .[wbgt]'); raise e
    if a.download:
        jurl=build_url(a.station,a.start,a.end)
        # Convertir fechas JST a un día anterior y posterior en UTC para incluir el borde de la jornada.
        wstart=(first-timedelta(days=1)).isoformat()
        wend=(last+timedelta(days=1)).isoformat()
        wurl=history_url(a.lat,a.lon,wstart,wend)
        print('Consultando Japón MOE:',jurl)
        j=fetch_japan(jurl)
        print('Consultando Open-Meteo histórico:',wurl)
        w=fetch_weather(wurl)
    else:
        j=json.loads(Path(a.japan_json).read_text(encoding='utf-8'))
        w=json.loads(Path(a.weather_json).read_text(encoding='utf-8'))
    folder=Path(a.out); folder.mkdir(parents=True,exist_ok=True)
    save_raw(folder/'japan_api_raw.json',j)
    save_raw(folder/'openmeteo_raw.json',w)
    result,pairs,refs,met=run_reference_study(j,w,station=a.station,site_id=a.site_id,
                         latitude=a.lat,longitude=a.lon,model=a.model,max_km=a.max_distance_km,
                         provenance_verified=a.download)
    save_outputs(folder,result,pairs,refs,met)
    print('Pares reales:',result['n_pairs'])
    print('MAE (°C):',result['metrics']['all']['mae_c'])
    print('Holdout:',result['temporal_holdout']['status'])
    print('Nota: la referencia japonesa contiene Tg observada y Tw estimada, NO es ISO natural wet bulb.')

if __name__=='__main__': main()
