"""Benchmark observacional y estudio de variables faltantes para HeatGuard.

SOLO se aceptan referencias japonesas filtradas por v0.9 (WBGT class=1, WI=4).
Métricas observacionales se emiten únicamente con >=6 días JST y datos horarios
compatibles. La estimación no equivale a validación del dispositivo ni de ISO 7243.

Uso:
  python -m heatguard.benchmark_v10 --download --station 44132 \
    --lat 35.69 --lon 139.76 --start 2025-08-01 --end 2025-08-14

  python -m heatguard.benchmark_v10 --japan-json data/japan.json \
    --weather-json data/openmeteo.json --station 44132 \
    --lat 35.69 --lon 139.76 --start 2025-08-01 --end 2025-08-14
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import random
from datetime import date, timedelta
from pathlib import Path
from statistics import mean

from .japan_api_v09 import build_url, fetch_json as fetch_japan, normalize_observed, sha256_json
from .weather_history_v07 import history_url, fetch_json as fetch_weather, normalize_openmeteo
from .independent_validation_v09 import pair_and_predict


SCENARIOS = {
    'regional_full': 'Todas las entradas regionales del reanálisis',
    'wind_fixed_1ms': 'Viento local hipotético fijo de 1,0 m/s (NO medición)',
    'solar_zero': 'Sombra idealizada: radiación de onda corta = 0 W/m2 (NO observación)',
    'solar_half': 'Radiación arbitrariamente reducida al 50 % (NO sensor)',
    'wind_fixed_solar_half': 'Viento supuesto 1 m/s y radiación al 50 %',
}


def scenario_weather(rows: list[dict], scenario: str) -> list[dict]:
    if scenario not in SCENARIOS:
        raise ValueError('Escenario desconocido')
    adjusted = []
    for r in rows:
        x = dict(r)
        if scenario in ('wind_fixed_1ms', 'wind_fixed_solar_half'):
            x['wind_speed_10m_m_s'] = 1.0
            x['wind_input_status'] = 'assumed_fixed_not_measured'
        if scenario == 'solar_zero':
            x['solar_w_m2'] = 0.0
            x['solar_input_status'] = 'assumed_zero_not_measured'
        elif scenario in ('solar_half', 'wind_fixed_solar_half'):
            x['solar_w_m2'] = x['solar_w_m2'] * 0.5
            x['solar_input_status'] = 'scenario_scaled_not_measured'
        x['scenario_id'] = scenario
        adjusted.append(x)
    return adjusted


def errors_metrics(pairs: list[dict]) -> dict | None:
    if not pairs:
        return None
    es = [float(p['error_c']) for p in pairs]
    n = len(es)
    under = [max(0., -e) for e in es]
    return {
        'n': n,
        'mae_c': round(mean(abs(e) for e in es), 4),
        'rmse_c': round(math.sqrt(mean(e*e for e in es)), 4),
        'bias_model_minus_reference_c': round(mean(es), 4),
        'underestimation_fraction': round(sum(e < 0 for e in es) / n, 4),
        'underestimation_gt_1c_fraction': round(sum(e < -1 for e in es) / n, 4),
        'underestimation_gt_2c_fraction': round(sum(e < -2 for e in es) / n, 4),
        'p90_underestimation_c': round(sorted(under)[min(n-1, math.ceil(.9*n)-1)], 4),
    }


def metrics_groups(pairs: list[dict]) -> dict:
    return {
        'all': errors_metrics(pairs),
        'sun_ghi_gt_20': errors_metrics([p for p in pairs if p.get('regional_original_solar_w_m2', p['solar_w_m2']) > 20]),
        'night_ghi_le_20': errors_metrics([p for p in pairs if p.get('regional_original_solar_w_m2', p['solar_w_m2']) <= 20]),
        'high_reference_ge_28c': errors_metrics([p for p in pairs if p['reference_c'] >= 28]),
    }


def bootstrap_day_mae_ci(pairs: list[dict], *, n_boot: int = 1000, seed: int = 42) -> dict | None:
    """Remuestreo por DIA, no por lectura horaria (correlación temporal)."""
    groups = {}
    for row in pairs:
        groups.setdefault(row['jst_day'], []).append(row)
    days = sorted(groups)
    if len(days) < 3:
        return None
    rng = random.Random(seed)
    estimates = []
    for _ in range(n_boot):
        sample = [r for _ in days for r in groups[rng.choice(days)]]
        estimates.append(mean(abs(float(x['error_c'])) for x in sample))
    estimates.sort()
    return {'method':'bootstrap_resampling_days_JST', 'days':len(days),
            'replicates':n_boot,
            'mae_ci95_c':[round(estimates[int(.025*n_boot)],4),
                           round(estimates[min(n_boot-1, math.ceil(.975*n_boot)-1)],4)]}


def temporal_evaluation(pairs: list[dict], *, min_days: int = 6, test_fraction: float = .3) -> dict:
    days = sorted({r['jst_day'] for r in pairs})
    if len(days) < min_days:
        return {'status':'blocked_insufficient_days','n_days':len(days),'min_days':min_days}
    cut = max(3, math.floor((1 - test_fraction)*len(days)))
    cut = min(cut, len(days)-3)
    trd = set(days[:cut]); ted = set(days[cut:])
    train = [r for r in pairs if r['jst_day'] in trd]
    test = [r for r in pairs if r['jst_day'] in ted]
    if len(train) < 24 or len(test) < 24:
        return {'status':'blocked_insufficient_pairs','n_train':len(train),'n_test':len(test)}
    # El sesgo solo se aprende de las primeras jornadas (evita fuga temporal).
    fitted_bias = mean(r['error_c'] for r in train)
    corrected = [{**r, 'error_c':r['error_c'] - fitted_bias} for r in test]
    return {
        'status':'evaluated', 'train_days':sorted(trd), 'test_days':sorted(ted),
        'n_train':len(train), 'n_test':len(test),
        'fitted_bias_train_c':round(fitted_bias,4),
        'test_uncorrected':metrics_groups(test),
        'test_after_train_only_bias_correction':metrics_groups(corrected),
        'test_uncorrected_bootstrap_by_day':bootstrap_day_mae_ci(test),
        'test_corrected_bootstrap_by_day':bootstrap_day_mae_ci(corrected),
    }


def benchmark_data(japan: dict, weather: dict, *, station: int, site_id: str,
                   latitude: float, longitude: float, model: str = 'ono',
                   claimed_official_download: bool = False, min_days: int = 6) -> tuple[dict,list[dict]]:
    if model not in ('ono','liljegren'):
        raise ValueError('Modelo no compatible')
    refs, q = normalize_observed(japan, station_no=station, site_id=site_id,
                                latitude_deg=latitude, longitude_deg=longitude)
    met = normalize_openmeteo(weather, session_id=f'JP_{station}')
    if not refs:
        raise ValueError('Sin referencias instrumentales parciales admisibles: class=1, WI=4')
    output: dict = {}
    primary_pairs: list[dict] = []
    original_ghi = {r['timestamp_utc']:r['solar_w_m2'] for r in met}
    for name in SCENARIOS:
        pairs, rejects = pair_and_predict(refs, scenario_weather(met, name), model=model)
        for row in pairs:
            row['regional_original_solar_w_m2'] = original_ghi[row['timestamp_utc']]
        if name == 'regional_full':
            primary_pairs = pairs
        group_days = len({r['jst_day'] for r in pairs})
        # Un modelo con pocas observaciones no es evidencia suficiente.
        if len(pairs) < 48 or group_days < min_days:
            output[name] = {
                'status':'blocked_insufficient_observations',
                'n_pairs':len(pairs),'n_days':group_days, 'rejected':rejects}
        else:
            output[name] = {'status':'evaluated', 'n_pairs':len(pairs), 'n_days':group_days,
                            'metrics':metrics_groups(pairs),
                            'temporal_holdout':temporal_evaluation(pairs,min_days=min_days),
                            'rejected':rejects}
    has_measures = output['regional_full']['status'] == 'evaluated'
    report = {
        'status': ('observational_metrics_from_current_download' if claimed_official_download else
                   'metrics_from_unverified_offline_files') if has_measures else 'blocked_no_publishable_metrics',
        'research_only':True, 'clip_hardware_validated':False,
        'is_ISO_7243_compliant_measurement':False,
        'reference_is_fully_independent_natural_wet_bulb':False,
        'reference_method':'Japan MOE: 6-inch globe observed; air observed; wet-bulb computed (NOT natural wet-bulb measured)',
        'station_id':station,'site_id':site_id,
        'coordinates_operator_supplied_not_station_master_verified':[latitude,longitude],
        'reference_quality_filter':'wbgt_class=1 and wbgt_WI=4',
        'japan_quality_counts':q,
        'meteorology':'Open-Meteo Historical reanalysis (hourly GHI preceding-hour average; wind 10m)',
        'download_verified_by_this_run':claimed_official_download,
        'offline_json_authenticity_not_verified':not claimed_official_download,
        'japan_json_sha256':sha256_json(japan),'weather_json_sha256':sha256_json(weather),
        'model':model,'scenarios':output,'scenario_descriptions':SCENARIOS,
        'causal_sensor_improvement_demonstrated':False,
        'known_limitations':[
            'Los datos meteorológicos provienen de la grilla regional: no equivalen a condiciones del clip.',
            'La serie de WBGT japonesa combina Tg medido con bulbo húmedo calculado.',
            'La radiación Open-Meteo es media de la hora anterior y puede no representar el instante de Tg.',
            'Los experimentos de ablation usan SUPUESTOS arbitrarios, NO características de sensores existentes.',
            'No realizar ajustes de modelos usando datos de las jornadas de evaluación.',
            'No emplear resultados de investigación para alertas o declaraciones de condiciones seguras.'
        ],
    }
    return report, primary_pairs


def save_report(outdir: str | Path, report:dict, pairs:list[dict]):
    path = Path(outdir); path.mkdir(parents=True, exist_ok=True)
    (path/'reporte_v10.json').write_text(json.dumps(report, ensure_ascii=False,indent=2),encoding='utf-8')
    table = ['# HeatGuard v0.10 — Evaluación observacional', '',
            f"**Estado:** `{report['status']}`. **Modelo:** {report['model']}. **Estación:** {report['station_id']}.",
            '', '**No corresponde a validación del clip ni certificación ISO 7243.**', '',
            '| Escenario | n | MAE °C | Sesgo °C | subestima más de 2 °C |',
            '|---|---:|---:|---:|---:|']
    for key, val in report['scenarios'].items():
        if val['status'] != 'evaluated':
            table.append(f'| {key} | {val["n_pairs"]} | No disponible | No disponible | No disponible |')
        else:
            metrics = val['metrics']['all']
            table.append(f'| {key} | {metrics["n"]} | {metrics["mae_c"]:.3f} | {metrics["bias_model_minus_reference_c"]:.3f} | {metrics["underestimation_gt_2c_fraction"]:.1%} |')
    table += ['', '## Limitaciones', *[f'- {s}' for s in report['known_limitations']], '',
              f"Fuente referencia: https://www.wbgt.env.go.jp/api/v1/getSurveyData",
              f"Fuente meteorología: https://archive-api.open-meteo.com/v1/archive", '']
    (path/'REPORTE.md').write_text('\n'.join(table),encoding='utf-8')
    if pairs:
        with (path/'pares_regionales.csv').open('w',newline='',encoding='utf-8') as f:
            writer = csv.DictWriter(f,fieldnames=list(pairs[0]));writer.writeheader();writer.writerows(pairs)


def main():
    p = argparse.ArgumentParser(description='Benchmark observacional v0.10: NO valida el dispositivo')
    p.add_argument('--station',type=int,default=44132)
    p.add_argument('--site-id',default='JP_TOKYO')
    p.add_argument('--lat',type=float,required=True)
    p.add_argument('--lon',type=float,required=True)
    p.add_argument('--start',required=True)
    p.add_argument('--end',required=True)
    p.add_argument('--model',choices=['ono','liljegren'],default='ono')
    p.add_argument('--download',action='store_true')
    p.add_argument('--japan-json')
    p.add_argument('--weather-json')
    p.add_argument('--urls-only',action='store_true')
    p.add_argument('--out',default='results/observational_v10')
    a=p.parse_args()
    first,last=date.fromisoformat(a.start),date.fromisoformat(a.end)
    if first>last or (last-first).days>31:
        p.error('Ventana de fechas inválida; máximo 32 días')
    jurl=build_url(a.station,a.start,a.end)
    wurl=history_url(a.lat,a.lon,(first-timedelta(days=1)).isoformat(),(last+timedelta(days=1)).isoformat())
    if a.urls_only:
        print('Japón:',jurl,'\nOpen-Meteo:',wurl)
        return
    if a.download == bool(a.japan_json or a.weather_json):
        p.error('Usar --download O AMBOS --japan-json y --weather-json')
    if not a.download and not (a.japan_json and a.weather_json):
        p.error('Los dos archivos son necesarios en modo local')
    if a.download:
        print('Descargando Japón y Open-Meteo; por favor respetar límites de solicitudes oficiales.')
        try:
            jap,met=fetch_japan(jurl),fetch_weather(wurl)
        except Exception as e:
            raise SystemExit(f'Sin datos descargados: {type(e).__name__}: {e}\nNO se generaron métricas.')
    else:
        jap=json.loads(Path(a.japan_json).read_text(encoding='utf-8'))
        met=json.loads(Path(a.weather_json).read_text(encoding='utf-8'))
    rep,pairs=benchmark_data(jap,met,station=a.station,site_id=a.site_id,
                            latitude=a.lat,longitude=a.lon,model=a.model,
                            claimed_official_download=a.download)
    dest=Path(a.out); dest.mkdir(parents=True,exist_ok=True)
    # Para repetibilidad se almacenan los originales de la respuesta (incluso si no hay pares suficientes)
    (dest/'japon_respuesta.json').write_text(json.dumps(jap,ensure_ascii=False),encoding='utf-8')
    (dest/'openmeteo_respuesta.json').write_text(json.dumps(met,ensure_ascii=False),encoding='utf-8')
    save_report(dest,rep,pairs)
    print('Estado:',rep['status'])
    print('Referencia Japón aceptada:',rep['japan_quality_counts']['accepted'])
    for name,x in rep['scenarios'].items():
        print(name, x['metrics']['all']['mae_c'] if x['status']=='evaluated' else 'BLOQUEADO')
    if rep['status'] == 'blocked_no_publishable_metrics':
        raise SystemExit('Muestras insuficientes: no se publica precisión experimental.')


if __name__ == '__main__':
    main()
