"""Laboratorio de sensibilidad y valor informativo de sensores.

Análisis de escenarios, NO incertidumbre calibrada ni rendimiento real del sensor.
Por defecto usa el balance simplificado de HeatGuard, no Liljegren. Con --model
liljegren se invoca el paquete de terceros con TODA la meteorología/metadata.
"""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path
import random
from typing import Any, Callable

from .thermal_science import experimental_balance_c
from .liljegren import calculate_optional

PARAMS = ('air_temperature_c', 'relative_humidity_pct', 'solar_w_m2', 'wind_speed_m_s', 'pressure_hpa')
UNITS = {
    'air_temperature_c': '°C', 'relative_humidity_pct': '%HR',
    'solar_w_m2': 'W/m²', 'wind_speed_m_s': 'm/s', 'pressure_hpa': 'hPa'
}
STEPS = {
    'air_temperature_c': 0.25, 'relative_humidity_pct': 1.0,
    'solar_w_m2': 25.0, 'wind_speed_m_s': 0.1, 'pressure_hpa': 2.0,
}
ALLOWED = {
    'air_temperature_c': (10, 48), 'relative_humidity_pct': (10, 95),
    'solar_w_m2': (0, 1200), 'wind_speed_m_s': (0.1, 8), 'pressure_hpa': (800, 1050)
}

DEFAULT_CASE = {
    'description': 'Escenario hipotético exterior soleado, no proveniente de una faena',
    'timestamp': '2026-11-11T17:00:00-03:00',
    'baseline': {
        'air_temperature_c': 32.0, 'relative_humidity_pct': 60.0,
        'solar_w_m2': 650.0, 'wind_speed_m_s': 1.5, 'pressure_hpa': 1008.0
    },
    'uncertainty_ranges': {
        'air_temperature_c': [31.7, 32.3],
        'relative_humidity_pct': [57.0, 63.0],
        'solar_w_m2': [100.0, 1000.0],
        'wind_speed_m_s': [0.2, 4.0],
        'pressure_hpa': [992.0, 1024.0],
    },
    'sensor_scenarios': {
        'sin_sensor_adicional': {},
        'sensor_radiacion_local': {'solar_w_m2': [570.0, 730.0]},
        'sensor_viento_local': {'wind_speed_m_s': [1.2, 1.8]},
        'ambos_sensores': {'solar_w_m2': [570.0, 730.0], 'wind_speed_m_s': [1.2, 1.8]},
        'sensor_presion': {'pressure_hpa': [1006.0, 1010.0]},
    },
    'liljegren_context': {
        'environment': 'outdoor',
        'location': {'latitude_deg': -33.45, 'longitude_deg': -70.65, 'utc_offset_hours': -3},
        'weather_model': {'wind_height_m': 10, 'averaging_minutes': 60,
                          'urban': 1, 'vertical_temperature_difference_c': 0},
    },
    'notes': 'Los rangos representan desconocimiento hipotético. No son errores certificados de sensores ni distribuciones de campo. Viento local para balance; a 10 m para Liljegren solo si lo especifica la fuente.'
}


def load_case(path: str | Path | None = None) -> dict:
    data = json.loads(Path(path).read_text(encoding='utf-8')) if path else json.loads(json.dumps(DEFAULT_CASE))
    base = data['baseline']
    ranges = data['uncertainty_ranges']
    if set(base) != set(PARAMS) or set(ranges) != set(PARAMS):
        raise ValueError(f'baseline y uncertainty_ranges deben contener exactamente {PARAMS}')
    for k in PARAMS:
        lo, hi = map(float, ranges[k]); bl = float(base[k]); a, b = ALLOWED[k]
        if not (a <= lo <= bl <= hi <= b):
            raise ValueError(f'Rango inválido para {k}: {lo}, {hi}, centro {bl}; dominio {a}..{b}')
    if 'sensor_scenarios' not in data or 'sin_sensor_adicional' not in data['sensor_scenarios']:
        raise ValueError('Se requiere sensor_scenarios.sin_sensor_adicional')
    for name, overrides in data['sensor_scenarios'].items():
        for k, bounds in overrides.items():
            if k not in PARAMS:
                raise ValueError(f'Parámetro desconocido {k} en {name}')
            lo, hi = map(float, bounds)
            if not (ALLOWED[k][0] <= lo <= float(base[k]) <= hi <= ALLOWED[k][1]):
                raise ValueError(f'Rango de {k} en {name} no incluye el valor base')
    return data


def model_function(case: dict, model: str) -> tuple[Callable[[dict], float], str]:
    if model == 'balance':
        def run(vals: dict) -> float:
            return experimental_balance_c(**vals)['wbgt_like_experimental_c']
        return run, 'heatguard_simplified_energy_balance_v1 (proxy, NO WBGT validado)'
    if model == 'liljegren':
        # No sustituimos lwbgt por un proxy silenciosamente.
        try:
            import lwbgt  # noqa: F401
        except ImportError as exc:
            raise RuntimeError('No está instalado lwbgt: pip install -e ".[wbgt]". '
                               'El experimento con balance simplificado funciona sin él.') from exc
        context = case.get('liljegren_context')
        if not isinstance(context, dict):
            raise ValueError('liljegren_context requerido para Liljegren')
        def run(vals: dict) -> float:
            result = calculate_optional(vals, case['timestamp'], context)
            if result['status'] != 'computed':
                raise RuntimeError(f'Liljegren no pudo ejecutarse: {result}')
            return float(result['value_c'])
        return run, 'Liljegren/lwbgt exterior modelado (NO medición ISO; metadatos requeridos)'
    raise ValueError('model debe ser balance o liljegren')


def quantile(values: list[float], fraction: float) -> float:
    if not values:
        raise ValueError('Sin valores')
    a = sorted(values)
    p = (len(a) - 1) * fraction
    i = int(p)
    if i == len(a) - 1:
        return a[i]
    return a[i] + (a[i+1] - a[i]) * (p-i)


def local_derivatives(base: dict, model_fn: Callable[[dict], float]) -> list[dict]:
    result = []
    for k in PARAMS:
        h = STEPS[k]; lo, hi = ALLOWED[k]
        left = max(lo, base[k] - h); right = min(hi, base[k] + h)
        x1, x2 = dict(base), dict(base)
        x1[k], x2[k] = left, right
        derivative = (model_fn(x2) - model_fn(x1)) / (right - left)
        result.append({'parameter': k, 'unit': UNITS[k], 'sensitivity_c_per_unit': round(derivative, 5),
                       'step': h, 'interpretation': 'derivada local, no importancia global del sensor'})
    return result


def compare_scenarios(case: dict, fn: Callable[[dict], float], *, samples: int = 400, seed: int = 42) -> list[dict]:
    if not 50 <= samples <= 5000:
        raise ValueError('samples debe estar entre 50 y 5000')
    names = list(case['sensor_scenarios'])
    rng = random.Random(seed)
    draws = [[rng.random() for _ in PARAMS] for _ in range(samples)]
    scenario_vals: dict[str, list[float]] = {}
    for name in names:
        merged = {**case['uncertainty_ranges'], **case['sensor_scenarios'][name]}
        outputs = []
        for u in draws:
            values = {key: float(merged[key][0]) + (float(merged[key][1]) - float(merged[key][0])) * u[i]
                      for i, key in enumerate(PARAMS)}
            outputs.append(fn(values))
        scenario_vals[name] = outputs
    baseline = scenario_vals['sin_sensor_adicional']
    base_width = quantile(baseline, 0.95) - quantile(baseline, 0.05)
    results = []
    for name, vals in scenario_vals.items():
        q05, q50, q95 = (quantile(vals, p) for p in (0.05, 0.5, 0.95))
        width = q95 - q05
        results.append({
            'scenario': name, 'samples': samples, 'q05_c': round(q05, 3),
            'median_c': round(q50, 3), 'q95_c': round(q95, 3),
            'scenario_spread_90_c': round(width, 3),
            'spread_reduction_vs_base_c': round(base_width - width, 3),
            'hypothetical_input_ranges': {k: list(map(float, case['sensor_scenarios'][name].get(k, case['uncertainty_ranges'][k]))) for k in PARAMS}
        })
    return results


def analyze(case: dict | None = None, *, model: str = 'balance', samples: int = 400, seed: int = 42) -> dict:
    case = load_case() if case is None else case
    # Validar configuraciones proporcionadas por API también.
    if case is not None:
        # validación sin E/S: mismas reglas que load_case
        if set(case['baseline']) != set(PARAMS):
            raise ValueError('baseline incompleto')
        for k in PARAMS:
            bl = float(case['baseline'][k]); lo, hi = map(float, case['uncertainty_ranges'][k])
            if not (ALLOWED[k][0] <= lo <= bl <= hi <= ALLOWED[k][1]):
                raise ValueError(f'Rango inválido: {k}')
        if 'sin_sensor_adicional' not in case['sensor_scenarios']:
            raise ValueError('Falta sin_sensor_adicional')
        for overrides in case['sensor_scenarios'].values():
            for k, bounds in overrides.items():
                if k not in PARAMS or len(bounds) != 2:
                    raise ValueError(f'Parámetro/rango inválido: {k}')
                lo, hi = map(float, bounds)
                if not (ALLOWED[k][0] <= lo <= float(case['baseline'][k]) <= hi <= ALLOWED[k][1]):
                    raise ValueError(f'Rango de sensor inválido: {k}')
    fn, model_name = model_function(case, model)
    base = {k: float(v) for k, v in case['baseline'].items()}
    baseline_estimate = fn(base)
    return {
        'purpose': 'research_only', 'normative_measurement': False,
        'safety_alerts_enabled': False, 'model': model_name,
        'description': case.get('description', ''),
        'baseline_inputs': base, 'baseline_model_output_c': round(baseline_estimate, 3),
        'local_derivatives': local_derivatives(base, fn),
        'scenario_comparison': compare_scenarios(case, fn, samples=samples, seed=seed),
        'analysis_settings': {'seed': seed, 'samples': samples, 'input_distribution': 'uniform_independent_hypothetical',
                              'interval': 'q05_to_q95_of_scenario_outputs; NOT statistical confidence/accuracy'},
        'unscored_candidate': 'termistor sobre carcasa: sin calibración física no se puede atribuir reducción del error WBGT',
        'limitations': [
            'La anchura q05-q95 es dispersión de escenarios inventados, NO incertidumbre calibrada del WBGT real.',
            'Los supuestos de viento, radiación y sus posibles errores se deben medir/justificar en campo.',
            'Reducir la dispersión de entradas NO demuestra que un sensor reduzca MAE contra WBGT de referencia.',
            'Sin referencia instrumental no se puede recomendar un sensor como definitivamente más preciso.',
        ]
    }


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open('w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def save_report(report: dict, dest: str | Path, *, plots: bool = True) -> list[Path]:
    path = Path(dest); path.mkdir(parents=True, exist_ok=True)
    json_path = path / 'sensitivity_report.json'
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    write_csv(path / 'scenario_comparison.csv', report['scenario_comparison'],
              ['scenario', 'samples', 'q05_c', 'median_c', 'q95_c', 'scenario_spread_90_c', 'spread_reduction_vs_base_c'])
    write_csv(path / 'local_derivatives.csv', report['local_derivatives'],
              ['parameter', 'unit', 'sensitivity_c_per_unit', 'step', 'interpretation'])
    md = [
        '# HeatGuard — análisis de sensibilidad (solo investigación)', '',
        f'**Modelo:** {report["model"]}',
        f'**Salida central de escenario:** {report["baseline_model_output_c"]:.2f} °C — NO es medición ISO.', '',
        '## Supuestos y alcance',
        'Las entradas y sus rangos son hipotéticos. Las bandas q05–q95 describen'
        ' la dispersión de escenarios bajo distribuciones uniformes independientes;'
        ' **NO** constituyen intervalos de confianza, precisión garantizada ni incertidumbre calibrada.', '',
        '## Comparación de opciones',
        '| Configuración | q05 (°C) | Mediana (°C) | q95 (°C) | Anchura central 90 % (°C) | Mejora de dispersión (°C) |',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for row in report['scenario_comparison']:
        md.append('| {} | {:.2f} | {:.2f} | {:.2f} | {:.2f} | {:.2f} |'.format(
            row['scenario'], row['q05_c'], row['median_c'], row['q95_c'], row['scenario_spread_90_c'],
            row['spread_reduction_vs_base_c']))
    md += ['', '## Interpretación',
           'La comparación solo evalúa cuánto cambiaría el **modelo** al reducir'
           ' ciertos rangos de entrada. NO estima MAE contra referencias de campo.',
           'El termistor de carcasa queda sin puntuar hasta existir una función de transferencia calibrada.', '',
           '## Próximos pasos',
           '1. Sustituir rangos inventados por incertidumbres medidas en cada zona.',
           '2. Ejecutar lwbgt/Liljegren instalado como segundo modelo y contrastar.',
           '3. Capturar sesiones sincronizadas de WBGT de referencia y ejecutar validation.py.',
           '4. Comparar error por sol/sombra, viento y montaje antes de elegir hardware.', '',
           '## Limitaciones', *[f'- {x}' for x in report['limitations']], '']
    (path / 'RESUMEN_RESULTADOS.md').write_text('\n'.join(md), encoding='utf-8')
    created = [json_path, path / 'scenario_comparison.csv', path / 'local_derivatives.csv', path / 'RESUMEN_RESULTADOS.md']
    if plots:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
        except ImportError:
            return created
        rows = report['scenario_comparison']
        labels = [r['scenario'].replace('_', ' ') for r in rows]
        center = [r['median_c'] for r in rows]
        lo = [r['median_c'] - r['q05_c'] for r in rows]
        hi = [r['q95_c'] - r['median_c'] for r in rows]
        fig, ax = plt.subplots(figsize=(10, 5.1))
        ax.errorbar(center, range(len(rows)), xerr=[lo, hi], fmt='o', capsize=4)
        ax.set_yticks(range(len(rows)), labels)
        ax.invert_yaxis()
        ax.set_xlabel('Salida del modelo (°C), intervalo central de escenarios 5–95 %')
        ax.set_title('HeatGuard — Dispersión hipotética por configuración\nNO indica exactitud contra referencia')
        ax.grid(axis='x', alpha=0.25)
        fig.tight_layout()
        fig.savefig(path / 'bandas_escenarios.png', dpi=160)
        plt.close(fig)
        created.append(path / 'bandas_escenarios.png')
        fig, ax = plt.subplots(figsize=(9.5, 5))
        ax.barh(labels, [r['spread_reduction_vs_base_c'] for r in rows])
        ax.invert_yaxis()
        ax.set_xlabel('Disminución de dispersión (°C), respecto a opción base')
        ax.set_title('Valor informativo hipotético de sensores\nNO es reducción de error MAE')
        ax.grid(axis='x', alpha=0.25)
        fig.tight_layout()
        fig.savefig(path / 'comparacion_sensores.png', dpi=160)
        plt.close(fig)
        created.append(path / 'comparacion_sensores.png')
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description='Sensibilidad HeatGuard: NO medición ISO ni validación de precisión')
    parser.add_argument('--case', type=str, default=None, help='JSON con hipótesis del experimento')
    parser.add_argument('--model', choices=['balance', 'liljegren'], default='balance')
    parser.add_argument('--samples', type=int, default=400)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--out', type=str, default='results/research')
    args = parser.parse_args()
    try:
        report = analyze(load_case(args.case), model=args.model, samples=args.samples, seed=args.seed)
    except (ValueError, KeyError, RuntimeError, ArithmeticError) as exc:
        parser.error(str(exc))
    paths = save_report(report, args.out)
    print(f'Modelo: {report["model"]}')
    print(f'Salida base (NO ISO): {report["baseline_model_output_c"]:.2f} °C')
    for row in report['scenario_comparison']:
        print(f'{row["scenario"]:28s} dispersión 90%: {row["scenario_spread_90_c"]:.2f} °C')
    print('Archivos guardados:')
    for p in paths: print('  -', p)


if __name__ == '__main__':
    main()
