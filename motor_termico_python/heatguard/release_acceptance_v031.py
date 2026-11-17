"""Aceptación integral v0.31 con GATT simulado, API real y SQLite.

No usa Bluetooth físico, sensores ni personas. Comprueba integración y fallas
de software; no exactitud térmica ni eficacia preventiva.
"""
from __future__ import annotations

import argparse
import copy
import csv
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import struct

from fastapi.testclient import TestClient

from . import api
from .ble_existing import ButtonEventTracker
from .fleet import FleetService
from .virtual_site import SITE_EXAMPLE, simulated_events


def run(db_path: str) -> dict:
    db = Path(db_path)
    if db.exists():
        raise FileExistsError(f'La base de aceptación debe ser nueva: {db}')
    db.parent.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 11, 15, 14, 0, tzinfo=timezone.utc)
    fleet = FleetService(str(db), scenario=SITE_EXAMPLE)
    previous = api._fleet
    api._fleet = fleet
    checks: list[dict] = []

    def check(name: str, passed: bool, detail: str = ''):
        checks.append({'check': name, 'passed': bool(passed), 'detail': detail})

    try:
        with TestClient(api.app) as client:
            admin = {'X-API-Key': 'acceptance-admin'}
            viewer = {'X-API-Key': 'acceptance-viewer'}
            events = list(simulated_events(devices=3, frames=4, interval_s=120, start=start))
            by_device: dict[str, list[dict]] = {}
            for event in events:
                by_device.setdefault(event['device_id'], []).append(event)
            accepted = 0
            for rows in by_device.values():
                for index, event in enumerate(rows):
                    event['context']['work_state'] = 'resting' if index in (1, 2) else 'working'
                    event['context']['activity_class'] = 'heavy'
                    response = client.post('/v1/live/ingest?scenario=true', json=event, headers=admin)
                    if response.status_code == 200 and response.json().get('accepted'):
                        accepted += 1
            check('multi_device_authenticated_ingest', accepted == 12, f'accepted={accepted}')
            estimator_states = {
                device: fleet.latest(device)['result']['environmental_estimator_v18']['status']
                for device in by_device
            }
            check('estimators_respect_environment',
                  estimator_states['HG-0101'] == 'computed' and
                  estimator_states['HG-0102'] == 'computed' and
                  estimator_states['HG-0103'] == 'not_applicable',
                  json.dumps(estimator_states, sort_keys=True))

            first_id = sorted(by_device)[0]
            latest = fleet.latest(first_id)['result']['exposure_timeline_v22']
            check('rest_separate_from_heavy_activity',
                  latest['minutes_declared_rest'] == 4 and latest['minutes_declared_work'] == 2,
                  f"work={latest['minutes_declared_work']}, rest={latest['minutes_declared_rest']}")

            duplicate = client.post('/v1/live/ingest?scenario=true', json=by_device[first_id][-1],
                                    headers=admin).json()
            check('telemetry_duplicate_rejected', duplicate.get('duplicate') is True)

            late = copy.deepcopy(by_device[first_id][1])
            late['event_id'] = 'acceptance-late-event'
            late['timestamp'] = (start + timedelta(minutes=1)).isoformat()
            late['context']['work_state'] = 'working'
            for observation in late['observations']:
                observation['timestamp'] = late['timestamp']
            late_response = client.post('/v1/live/ingest?scenario=true', json=late, headers=admin)
            late_timeline = late_response.json()['result']['exposure_timeline_v22']
            check('late_event_ordered_without_rewind', late_response.status_code == 200 and
                  late_timeline['out_of_order_samples'] >= 1 and
                  late_timeline['current_work_state'] == 'working')

            gap = copy.deepcopy(by_device[first_id][-1])
            gap['event_id'] = 'acceptance-after-gap'
            gap['timestamp'] = (start + timedelta(minutes=20)).isoformat()
            gap['context']['work_state'] = 'working'
            for observation in gap['observations']:
                observation['timestamp'] = gap['timestamp']
            gap_response = client.post('/v1/live/ingest?scenario=true', json=gap, headers=admin).json()
            gap_timeline = gap_response['result']['exposure_timeline_v22']
            check('connectivity_gap_unknown_not_rest',
                  gap_timeline['missing_minutes'] == 14 and
                  gap_timeline['minutes_declared_rest'] == 4,
                  f"missing={gap_timeline['missing_minutes']}")

            tracker = ButtonEventTracker(first_id)
            button_event = tracker.ingest(struct.pack('<BBH', 1, 2, 1),
                                          start + timedelta(minutes=5))[0]
            button_response = client.post('/v1/fleet/device-events', json=button_event,
                                          headers=admin).json()
            button_duplicate = client.post('/v1/fleet/device-events', json=button_event,
                                           headers=admin).json()
            check('hydration_self_report_persisted', button_response.get('accepted') is True and
                  button_event['physiological_measurement'] is False)
            check('button_counter_deduplicated', button_duplicate.get('duplicate') is True)

            unauthorized = client.post('/v1/live/ingest?scenario=true', json=gap)
            forbidden = client.post('/v1/live/ingest?scenario=true', json=gap, headers=viewer)
            check('api_authentication_enforced', unauthorized.status_code == 401 and
                  forbidden.status_code == 403)

            panel_data = client.get('/v1/mvp/devices', headers=viewer)
            panel_html = client.get('/mvp')
            first_panel = next(item for item in panel_data.json()['devices']
                               if item['device_id'] == first_id)
            check('panel_backend_integrated', panel_data.status_code == 200 and
                  panel_html.status_code == 200 and first_panel['hydration_self_report_count'] == 1)
            check('provenance_and_quality_visible', bool(first_panel['measurement_sources']) and
                  'engineering_quality' in first_panel and 'connectivity' in first_panel)
            check('no_automatic_actuator', all(
                row['result']['review_state_v23']['automatic_actuator_command'] is False
                for row in fleet.repository.latest(limit=100)))

            count_before = fleet.repository.count()
            restarted = FleetService(str(db), scenario=SITE_EXAMPLE)
            api._fleet = restarted
            after_restart = client.get('/v1/mvp/devices', headers=viewer).json()['devices']
            restored = next(item for item in after_restart if item['device_id'] == first_id)
            check('restart_preserves_without_duplicate', restarted.repository.count() == count_before and
                  restored['hydration_self_report_count'] == 1)
            check('three_devices_after_restart', len(after_restart) == 3)
    finally:
        api._fleet = previous

    status = 'passed' if all(item['passed'] for item in checks) else 'failed'
    return {
        'status': status, 'software_release': '0.31.0',
        'simulation_only': True, 'physical_ble_used': False,
        'physical_hardware_used': False, 'occupational_validation_performed': False,
        'scenario': 'GATT simulado → API autenticada → SQLite → estimación → exposición → panel',
        'device_count': 3, 'checks': checks,
        'passed_checks': sum(item['passed'] for item in checks),
        'failed_checks': sum(not item['passed'] for item in checks),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    os.environ['HG_ADMIN_API_KEY'] = 'acceptance-admin'
    os.environ['HG_VIEWER_API_KEY'] = 'acceptance-viewer'
    report = run(args.db)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out / 'RELEASE_ACCEPTANCE_V031.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    with (out / 'checks_v031.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['check', 'passed', 'detail'])
        writer.writeheader(); writer.writerows(report['checks'])
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if report['status'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
