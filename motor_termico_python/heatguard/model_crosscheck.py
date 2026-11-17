"""Comparar proxy y Liljegren SIN equipararlos ni crear referencias ficticias.

La diferencia entre modelos NO es un error de precisión: se requiere un WBGT
medido para estimar error y sesgo, y viento a la altura especificada.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .liljegren import calculate_optional
from .sensitivity import load_case
from .thermal_science import experimental_balance_c


def compare(case: dict) -> dict:
    context = case.get('liljegren_context', {})
    weather = context.get('weather_model', {})
    wind_height = weather.get('wind_height_m')
    # El balance de v0.5 solo se interpreta con viento local del trabajador.
    # Para comparar modelos con un mismo número sin conversiones implícitas,
    # exigimos un viento local caracterizado a 2m.
    if wind_height != 2:
        return {'status': 'incompatible_wind_metadata',
                'reason': 'El balance usa viento local y Liljegren está configurado para altura diferente de 2 m. '
                          'No compararemos ambos como si compartieran condición meteorológica.',
                'provided_wind_height_m': wind_height,
                'reference_measured': False}
    inp = case['baseline']
    proxy = experimental_balance_c(**{
        'air_temperature_c': inp['air_temperature_c'],
        'relative_humidity_pct': inp['relative_humidity_pct'],
        'solar_w_m2': inp['solar_w_m2'],
        'wind_speed_m_s': inp['wind_speed_m_s'],
        'pressure_hpa': inp['pressure_hpa'],
    })
    liljegren = calculate_optional(inp, case['timestamp'],context)
    result={'status': 'models_compared' if liljegren['status']=='computed' else 'liljegren_not_computed',
            'proxy_balance_c':proxy['wbgt_like_experimental_c'],
            'liljegren':liljegren, 'reference_measured':False,
            'interpretation':'La diferencia entre modelos NO es error contra WBGT de referencia y no certifica a ninguno.'}
    if liljegren['status']=='computed':
        result['difference_proxy_minus_liljegren_c']=round(proxy['wbgt_like_experimental_c']-liljegren['value_c'],4)
    return result


def main():
    p=argparse.ArgumentParser(description='Comparación de modelos sin mezclar viento 10m/local')
    p.add_argument('--case',required=True); p.add_argument('--out',default='results/model_comparison_v06.json')
    args=p.parse_args()
    case=load_case(args.case)
    result=compare(case)
    dest=Path(args.out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
