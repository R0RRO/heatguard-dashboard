"""Extrae pares WBGT modelo/referencia de sesiones reales, SIN inventar etiquetas."""
from __future__ import annotations
import argparse
import csv
from pathlib import Path
from .repository import EventRepository
from .ml import FEATURES, TARGET, GROUP


def export_reference_pairs(db_file: str, output_csv: str) -> dict:
    output = Path(output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    count, discarded = 0, 0
    fields = [GROUP, 'reference_instrument_id', 'reference_measured', *FEATURES, TARGET]
    with output.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in EventRepository(db_file).iter_all():
            event, result = row['event'], row['result']
            if event.get('transport_metadata', {}).get('simulated'):
                discarded += 1
                continue
            observations = event.get('observations', [])
            reference = next((o for o in observations if o.get('parameter') == 'wbgt_reference_c'
                              and o.get('kind') == 'measured'
                              and o.get('metadata', {}).get('instrument_id')), None)
            wbgt = result.get('wbgt_outdoor_model', {})
            ctx = event.get('context', {})
            session = ctx.get('validation_session_id')
            selected = result.get('inputs_selected', {})
            values = {k: selected.get(k, {}).get('value') for k in FEATURES if k != 'wbgt_physical_c'}
            if (not reference or wbgt.get('status') != 'computed' or not session
                or any(v is None for v in values.values())
                or any(selected.get(k, {}).get('kind') in ('assumed', 'neighbor', 'estimated')
                       for k in values)):
                discarded += 1
                continue
            values['wbgt_physical_c'] = wbgt['value_c']
            writer.writerow({GROUP: session,
                             'reference_instrument_id': reference['metadata']['instrument_id'],
                             'reference_measured': 'true', **values,
                             TARGET: reference['value']})
            count += 1
    return {'exported': count, 'discarded': discarded, 'csv': str(output),
            'warning': 'Pares etiquetados requieren revisión de alineación temporal y calibración.'}


def main():
    p = argparse.ArgumentParser(description='Exportar pares reales para entrenar corrección ML')
    p.add_argument('--db', default='data/heatguard_v04.sqlite')
    p.add_argument('--out', default='data/reference_pairs.csv')
    args = p.parse_args()
    print(export_reference_pairs(args.db, args.out))


if __name__ == '__main__':
    main()
