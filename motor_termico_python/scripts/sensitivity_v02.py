"""Barrido en solar y viento (SOLO escenarios teóricos) con Liljegren.

Uso: python scripts/sensitivity_v02.py [--csv reporte.csv]
No es análisis de error frente a WBGT medido; NO es índice de seguridad.
"""
from __future__ import annotations
import argparse
import copy
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from heatguard import evaluate

ROOT = Path(__file__).resolve().parents[1]


def run_grid():
    base = json.loads((ROOT / 'examples' / 'outdoor_scenario.json').read_text(encoding='utf-8'))
    records = []
    for wind in (0.3, 1.0, 3.0):
        for solar in (200.0, 650.0, 900.0):
            event = copy.deepcopy(base)
            for entry in event['observations']:
                if entry['parameter'] == 'wind_speed_m_s':
                    entry['value'] = wind
                if entry['parameter'] == 'solar_w_m2':
                    entry['value'] = solar
            model = evaluate(event)['wbgt_outdoor_model']
            if model['status'] != 'computed':
                return None, model
            records.append({
                'wind_m_s_assumed': wind, 'solar_w_m2_assumed': solar,
                'wbgt_liljegren_c_experimental': model['value_c'],
            })
    return records, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', type=Path, help='Archivo CSV opcional')
    args = ap.parse_args()
    records, error = run_grid()
    if error:
        print('No es posible el barrido. Estado del modelo:', json.dumps(error, ensure_ascii=False))
        print('Instala dependencia opcional: python -m pip install -e ".[wbgt]"')
        return
    print('ESCENARIOS HIPOTÉTICOS. Resultados modelados, NO mediciones WBGT.\n')
    for row in records:
        print(f"v={row['wind_m_s_assumed']:.1f} m/s | G={row['solar_w_m2_assumed']:.0f} W/m2 "
              f"| WBGT modelo={row['wbgt_liljegren_c_experimental']:.2f} °C")
    low = min(r['wbgt_liljegren_c_experimental'] for r in records)
    high = max(r['wbgt_liljegren_c_experimental'] for r in records)
    # Rangos marginales por variable: escala comparativa, NO precisión de sensor.
    by_wind = {wind: [r['wbgt_liljegren_c_experimental'] for r in records
                     if r['wind_m_s_assumed'] == wind] for wind in (0.3, 1.0, 3.0)}
    by_solar = {solar: [r['wbgt_liljegren_c_experimental'] for r in records
                       if r['solar_w_m2_assumed'] == solar] for solar in (200.0, 650.0, 900.0)}
    wind_range = max(sum(v)/len(v) for v in by_wind.values()) - min(sum(v)/len(v) for v in by_wind.values())
    solar_range = max(sum(v)/len(v) for v in by_solar.values()) - min(sum(v)/len(v) for v in by_solar.values())
    print(f'\nAmplitud total escogida: {low:.2f} a {high:.2f} °C')
    print(f'Variación media entre vientos ensayados: {wind_range:.2f} °C')
    print(f'Variación media entre radiaciones ensayadas: {solar_range:.2f} °C')
    print('Estas amplitudes NO equivalen a incertidumbre, exactitud ni reducción de MAE.')
    if args.csv:
        with args.csv.open('w', newline='', encoding='utf-8') as fp:
            w = csv.DictWriter(fp, fieldnames=list(records[0].keys()))
            w.writeheader(); w.writerows(records)
        print('CSV generado:', args.csv)


if __name__ == '__main__':
    main()
