"""Comparación de dos MODELOS, no con instrumentos. Requires lwbgt instalado."""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path
from statistics import mean
from .weather_history_v07 import load_weather_csv
from .research_history_v07 import _estimate
from .sensitivity import quantile


def compare_models(rows: list[dict], *, roughness_m: float = .1, urban: int = 1) -> dict:
    try:
        import lwbgt  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("No está instalado lwbgt; no se sustituye silenciosamente") from exc
    pairs = []
    rejects = []
    for row in rows:
        ts = str(row["timestamp_utc"])
        try:
            solar, wind = float(row["solar_w_m2"]), float(row["wind_speed_10m_m_s"])
            proxy = _estimate(row, 'balance', solar, wind, roughness_m, urban)
            physical = _estimate(row, 'liljegren', solar, wind, roughness_m, urban)
            pairs.append({'timestamp_utc': ts, 'balance_proxy_c': proxy,
                          'liljegren_wbgt_model_c': physical,
                          'difference_proxy_minus_liljegren_c': proxy - physical,
                          'data_origin': row['data_origin']})
        except (ValueError, ArithmeticError) as exc:
            rejects.append({'timestamp_utc': ts, 'reason': str(exc)})
    if not pairs:
        raise ValueError('No se pudieron comparar los modelos')
    diff = [p['difference_proxy_minus_liljegren_c'] for p in pairs]
    return {
        'reference_measured': False, 'model_comparison_only': True, 'n': len(pairs),
        'mean_difference_c': round(mean(diff), 4),
        'mean_abs_difference_c': round(mean(abs(d) for d in diff), 4),
        'p90_abs_difference_c': round(quantile([abs(d) for d in diff], .9), 4),
        'roughness_m_for_wind_2m_proxy': roughness_m,
        'wind_10m_used_by_liljegren': True,
        'pairs': pairs, 'rejected': rejects,
        'interpretation': 'Diferencia entre modelos con parámetros/hipótesis propios, NO error físico ni exactitud del clip.',
    }


def main() -> None:
    p = argparse.ArgumentParser(description='Comparación Liljegren vs proxy con ajuste documentado de altura de viento')
    p.add_argument('--weather', required=True)
    p.add_argument('--roughness-m', type=float, default=.1)
    p.add_argument('--urban', type=int, default=1, choices=(0,1))
    p.add_argument('--out', default='results/crosscheck_v07.json')
    args = p.parse_args()
    result = compare_models(load_weather_csv(args.weather), roughness_m=args.roughness_m, urban=args.urban)
    dst = Path(args.out);dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Diferencia MAE modelo-modelo: {result["mean_abs_difference_c"]} °C; NO es MAE contra WBGT medido')

if __name__ == '__main__': main()
