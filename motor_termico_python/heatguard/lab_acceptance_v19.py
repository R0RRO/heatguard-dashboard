"""Prueba de aceptación sin hardware: tramas GATT binarias -> SQLite -> estimador.

Reproduce el formato de *heatguard_demo.ino*; NO es una conexión BLE ni
certifica precisión del sensor. Usa cuatro escenarios transparentes y controlados.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import struct
from uuid import uuid4

from .ble_existing import ExistingClipAssembler, TEMP_UUID, HUM_UUID, BAT_UUID, PACKET_UUID
from .fleet import FleetService
from .virtual_site import SITE_EXAMPLE

SCENARIOS = (
    ('HG-LAB-01', 'outdoor', 'exterior_con_hipotesis', True, 'variation'),
    ('HG-LAB-02', 'outdoor', 'exterior_sin_radiacion_viento', False, 'variation'),
    ('HG-LAB-03', 'indoor', 'interior', True, 'variation'),
    ('HG-LAB-04', 'outdoor', 'lectura_constante', True, 'constant'),
)


def _gatt_packets(index: int, mode: str) -> tuple[tuple[str, bytes], ...]:
    """Todas las cargas son ficticias, pero respetan el protocolo binario real."""
    t_c = 30.25 if mode == 'constant' else 30.25 + index * 0.11
    rh = 55.75 if mode == 'constant' else 55.75 + (index % 3) * 0.12
    return (
        (PACKET_UUID, struct.pack('<IhhhH', index * 4, 850, -30, 45, 1013)),
        (BAT_UUID, bytes([min(100, max(0, 91 - index // 5))])),
        (TEMP_UUID, struct.pack('<h', round(t_c * 100))),
        (HUM_UUID, struct.pack('<H', round(rh * 100))),
    )


def _simulated(event: dict, event_id: str) -> dict:
    event['event_id'] = event_id
    event['transport_metadata'].update({
        'simulated': True,
        'simulation_type': 'binary_gatt_lab_fixture_v19',
        'not_a_physical_ble_connection': True,
    })
    for obs in event['observations']:
        obs['kind'] = 'assumed'
        obs['source'] = 'GATT_BYTES_SIMULATED_NOT_MEASURED'
        obs['metadata'] = {'simulated': True, 'protocol': 'heatguard_demo'}
    return event


def run_lab(*, out: str | Path, db: str | Path | None = None,
            frames: int = 8, start: datetime | None = None,
            run_id: str | None = None) -> dict:
    if not 6 <= frames <= 100:
        raise ValueError('frames debe estar entre 6 y 100 para comprobar constancia de lecturas')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    start = start or datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=(frames - 1) * 15)
    if start.tzinfo is None:
        raise ValueError('La fecha de inicio requiere zona horaria')
    run_id = run_id or uuid4().hex[:10]
    db_path = Path(db) if db else (out / 'laboratorio.sqlite')
    fleet = FleetService(db_path=str(db_path), scenario=SITE_EXAMPLE)
    accepted: list[dict] = []
    packets: list[dict] = []
    events: list[dict] = []
    results: list[dict] = []

    for dev, environment, zone, use_scenario, mode in SCENARIOS:
        # Identidad de laboratorio distinta por ejecución: evita mezclar historial
        # de dos simulaciones independientes en una base de datos compartida.
        lab_device_id = f'{dev}-{run_id}'
        assembler = ExistingClipAssembler(device_id=lab_device_id, zone_id=zone, environment=environment)
        for i in range(frames):
            timestamp = start + timedelta(seconds=i * 15)
            for uuid, data in _gatt_packets(i, mode):
                packets.append({'device_id': lab_device_id, 'timestamp_utc': timestamp.isoformat(),
                                'uuid': uuid, 'data_hex': data.hex(), 'simulated': True})
                event = assembler.ingest(uuid, data, timestamp=timestamp)
                if event is None:
                    continue
                event = _simulated(event, f'v19-{run_id}-{dev}-{i:03d}')
                events.append(event)
                response = fleet.ingest(event, use_scenario=use_scenario)
                if not response.get('accepted'):
                    raise RuntimeError(f'Evento esperado no aceptado: {dev} frame {i}: {response}')
                result = response['result']
                results.append(result)
                env = result['environmental_estimator_v18']
                quality = result['engineering_quality_v19']
                accepted.append({
                    'device_id': lab_device_id, 'frame': i, 'timestamp_utc': event['timestamp'],
                    'environment': environment, 'with_scenario': use_scenario,
                    'estimated_wbgt_status': env['status'],
                    'estimated_wbgt_c': env.get('value_c'),
                    'input_quality': env.get('input_quality', {}).get('category'),
                    'engineering_quality_status': quality['status'],
                    'engineering_flags': ';'.join(quality['flag_codes']),
                    'simulated': True, 'occupational_alerts_enabled': False,
                })

    # Tres fallos de transporte inyectados: NO deben producir un evento aceptado.
    checks: list[dict] = []
    trial = ExistingClipAssembler('HG-LAB-FAULT', 'zona_prueba', 'outdoor')
    bad = False
    try:
        trial.ingest(TEMP_UUID, b'\x01\x02\x03', start)
    except ValueError:
        bad = True
    checks.append({'check': 'wrong_length_temperature', 'passed': bad,
                   'detail': 'Payload de 3 bytes rechazado antes de registrar telemetría'})
    test_time = start + timedelta(seconds=frames * 15)
    assert trial.ingest(TEMP_UUID, struct.pack('<h', 3000), test_time) is None
    old_pair = trial.ingest(HUM_UUID, struct.pack('<H', 5000), test_time + timedelta(seconds=8))
    checks.append({'check': 'out_of_sync_sensor_pair', 'passed': old_pair is None,
                   'detail': 'T y RH desfasadas 8 s no forman un evento BLE'})
    scene_by_dev = {dev: [r for r in accepted if r['device_id'].startswith(dev + '-')] for dev, *_ in SCENARIOS}
    checks += [
        {'check': 'outdoor_scenario_calculates_ono', 'passed': all(r['estimated_wbgt_status'] == 'computed' and r['input_quality'] == 'scenario_only' for r in scene_by_dev['HG-LAB-01']), 'detail': 'Sin encubrir hipótesis como medición'},
        {'check': 'without_wind_solar_no_wbgt', 'passed': all(r['estimated_wbgt_status'] == 'missing_inputs' for r in scene_by_dev['HG-LAB-02']), 'detail': 'No inventar viento ni radiación'},
        {'check': 'indoor_disables_outdoor_model', 'passed': all(r['estimated_wbgt_status'] == 'not_applicable' for r in scene_by_dev['HG-LAB-03']), 'detail': 'No extrapolar un modelo exterior a interiores'},
        {'check': 'flatline_flagged_not_diagnosed', 'passed': any('POSSIBLE_FLATLINE' in r['engineering_flags'] for r in scene_by_dev['HG-LAB-04']), 'detail': 'Constancia sospechosa no equivale a fallo confirmado'},
        {'check': 'simulated_never_measured', 'passed': all(r['simulated'] and not r['occupational_alerts_enabled'] for r in accepted) and all(all(o['kind'] == 'assumed' for o in e['observations']) for e in events), 'detail': 'Telemetría artificial siempre etiquetada'},
        {'check': 'all_events_persisted', 'passed': fleet.repository.count() >= len(accepted), 'detail': 'Persistencia SQLite activa'},
    ]
    for name, rows in [('gatt_packets.jsonl', packets), ('events.jsonl', events), ('results.jsonl', results)]:
        with (out / name).open('w', encoding='utf-8') as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
    with (out / 'dashboard_cases.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(accepted[0]))
        writer.writeheader()
        writer.writerows(accepted)
    summary = {
        'status': 'passed' if all(c['passed'] for c in checks) else 'failed',
        'experiment': 'HeatGuard GATT-to-estimator laboratory acceptance v0.19',
        'simulation_only': True, 'physical_hardware_used': False,
        'occupational_safety_system_validated': False,
        'run_id': run_id, 'devices': len(SCENARIOS), 'frames_per_device': frames,
        'gatt_notifications': len(packets), 'accepted_events': len(accepted),
        'storage': str(db_path), 'checks': checks,
        'note': 'El ensayo prueba la cadena de software con bytes sintéticos, no la exactitud del HTU21D ni el WBGT de faena.',
    }
    (out / 'ACCEPTANCE_REPORT.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'ACEPTACION.md').write_text(
        '# HeatGuard v0.19 — Ensayo de integración sin hardware\n\n'
        f'Estado: **{summary["status"]}**. {len(accepted)} eventos recibidos y almacenados.\n\n'
        'Los paquetes corresponden a la codificación binaria del firmware heatguard_demo, pero fueron generados en Python; no se conectó Bluetooth ni se verificó ningún sensor físico.\n\n'
        + '\n'.join(f'- {"OK" if c["passed"] else "FALLO"}: `{c["check"]}` — {c["detail"]}' for c in checks)
        + '\n\n**Nunca utilizar este ensayo para justificar alertas laborales automáticas.**\n',
        encoding='utf-8')
    if summary['status'] != 'passed':
        raise RuntimeError(f'Ensayo de laboratorio con comprobaciones fallidas: {out / "ACCEPTANCE_REPORT.json"}')
    return summary


def main():
    p = argparse.ArgumentParser(description='Prueba integrada GATT sintético -> backend -> SQLite, SIN hardware')
    p.add_argument('--out', default='results/aceptacion_v19')
    p.add_argument('--db', default='', help='Ruta SQLite; si se omite se crea dentro de --out')
    p.add_argument('--frames', type=int, default=8)
    args = p.parse_args()
    report = run_lab(out=args.out, db=args.db or None, frames=args.frames)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
