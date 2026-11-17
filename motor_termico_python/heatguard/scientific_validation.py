"""Evaluación EXCLUSIVAMENTE contra pares de un instrumento de referencia.

No intenta deducir etiquetas a partir de estaciones meteorológicas/simulaciones.
La metadata declarada debe auditarse manualmente (no prueba autenticidad).
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import csv
import json
import math
from pathlib import Path
from statistics import mean
from .sensitivity import load_case, model_function, PARAMS, quantile

REQUIRED = ('sample_id', 'session_id', 'reference_instrument_id', 'reference_origin',
            'timestamp', 'wbgt_reference_c', *PARAMS)


def _metrics(rows: list[dict]) -> dict:
    err = [r['error_c'] for r in rows]
    absolute = [abs(x) for x in err]
    return {
        'n': len(err), 'MAE_c': round(mean(absolute), 4),
        'RMSE_c': round(math.sqrt(mean([x*x for x in err])), 4),
        'bias_model_minus_reference_c': round(mean(err), 4),
        'absolute_error_p90_c': round(quantile(absolute, 0.90), 4),
        'max_absolute_error_c': round(max(absolute), 4),
    }


def evaluate_csv(csv_path: str | Path, *, model: str = 'balance', case_path: str | None = None) -> dict:
    case = load_case(case_path)
    model_fn, model_name = model_function(case, model)
    if model == 'liljegren':
        from .liljegren import calculate_optional
        def evaluate_single(vals: dict, timestamp: str) -> float:
            response = calculate_optional(vals, timestamp, case['liljegren_context'])
            if response['status'] != 'computed':
                raise ValueError(f'Liljegren no pudo evaluarse a {timestamp}: {response}')
            return float(response['value_c'])
    else:
        def evaluate_single(vals: dict, timestamp: str) -> float:
            return model_fn(vals)
    rows: list[dict] = []
    seen: set[str] = set()
    with Path(csv_path).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or any(c not in reader.fieldnames for c in REQUIRED):
            raise ValueError(f'El CSV requiere columnas {REQUIRED}')
        for line, raw in enumerate(reader, start=2):
            if not any((v or '').strip() for v in raw.values() if isinstance(v, str)):
                continue
            if raw['reference_origin'] != 'measured_instrument':
                raise ValueError(f'Fila {line}: reference_origin debe ser measured_instrument; no simular referencias.')
            if not raw['reference_instrument_id'].strip() or not raw['session_id'].strip():
                raise ValueError(f'Fila {line}: se requiere instrumento y sesión de referencia.')
            from .schema import iso_datetime
            iso_datetime(raw['timestamp'])
            sample = raw['sample_id'].strip()
            if not sample or sample in seen:
                raise ValueError(f'Fila {line}: sample_id duplicado o vacío')
            seen.add(sample)
            try:
                inputs = {k: float(raw[k]) for k in PARAMS}
                reference = float(raw['wbgt_reference_c'])
            except (ValueError, TypeError) as exc:
                raise ValueError(f'Fila {line}: entrada no numérica') from exc
            if not math.isfinite(reference) or not -40 <= reference <= 90:
                raise ValueError(f'Fila {line}: valor de referencia no plausible')
            estimated = evaluate_single(inputs, raw['timestamp'])
            rows.append({'sample_id': sample, 'session_id': raw['session_id'],
                         'reference_instrument_id': raw['reference_instrument_id'],
                         'wbgt_reference_c': reference, 'estimate_c': estimated,
                         'error_c': estimated - reference, 'solar_w_m2': inputs['solar_w_m2'],
                         'wind_speed_m_s': inputs['wind_speed_m_s']})
    if not rows:
        raise ValueError('No hay pares de medición en CSV')
    by_session: dict[str, list] = defaultdict(list)
    for row in rows:
        by_session[row['session_id']].append(row)
    return {
        'status': 'model_evaluated_against_declared_instrument',
        'model': model_name, 'measurement_conformity_iso': False,
        'metadata_unverified': True,
        'summary': _metrics(rows),
        'session_metrics': {k: _metrics(v) for k,v in sorted(by_session.items())},
        'solar_groups': {group: _metrics([r for r in rows if (r['solar_w_m2'] >= 300) == (group == 'solar_300_or_more')])
                         for group in ('solar_below_300', 'solar_300_or_more')
                         if any((r['solar_w_m2'] >= 300) == (group == 'solar_300_or_more') for r in rows)},
        'records': rows,
        'limitations': [
            'La etiqueta measured_instrument proviene del archivo y NO demuestra autenticidad de instrumentos.',
            'Evaluar separado por sitio/jornada y luego mantener sitios enteros fuera del ajuste ML.',
            'Sin certificados, protocolo de montaje ni alineación temporal, las métricas NO prueban ISO.',
        ],
    }


def main() -> None:
    parser=argparse.ArgumentParser(description='Evaluar WBGT modelado contra instrumento real, nunca etiquetas simuladas')
    parser.add_argument('--csv', required=True)
    parser.add_argument('--model', choices=['balance','liljegren'],default='balance')
    parser.add_argument('--case',default=None)
    parser.add_argument('--out',default='results/reference_validation.json')
    args=parser.parse_args()
    try:
        result=evaluate_csv(args.csv,model=args.model,case_path=args.case)
    except (ValueError,KeyError,RuntimeError) as exc:
        parser.error(str(exc))
    dest=Path(args.out); dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result['summary'],ensure_ascii=False,indent=2))
    print('Reporte:',dest)


if __name__=='__main__':
    main()
