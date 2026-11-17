from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import struct
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from fastapi.testclient import TestClient
import pytest

from heatguard import api
from heatguard.ble_existing import (
    ButtonEventTracker, BUTTON_UUID, MOTOR_UUID, decode_button_notification,
    encode_led_command, encode_motor_command,
)
from heatguard.exposure_v22 import DeviceExposureV22
from heatguard.fleet import FleetService
from heatguard.gateway_delivery import GatewayDelivery
from heatguard.radiation_v22 import prepare_radiation
from heatguard.virtual_site import SITE_EXAMPLE, simulated_events


T0 = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


class _UrlopenResponse:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.body


def _testclient_urlopen(client: TestClient, expected_key: str):
    def call(request, timeout=0):
        assert timeout > 0
        assert request.get_header('X-api-key') == expected_key
        response = client.post(request.full_url.replace('http://testserver', ''),
                               content=request.data,
                               headers={'Content-Type': 'application/json',
                                        'X-API-Key': expected_key})
        assert response.status_code == 200, response.text
        return _UrlopenResponse(response.content)
    return call


def test_authenticated_gateway_outbox_to_api_and_database(tmp_path: Path):
    fleet = FleetService(str(tmp_path / 'api.sqlite'), scenario=SITE_EXAMPLE)
    event = next(simulated_events(devices=1, frames=1, start=T0))
    delivery = GatewayDelivery(str(tmp_path / 'outbox.sqlite'), api_key='gateway-secret')
    with patch.object(api, '_fleet', fleet), \
         patch.dict('os.environ', {'HG_ADMIN_API_KEY': 'gateway-secret',
                                   'HG_VIEWER_API_KEY': 'viewer-secret'}), \
         TestClient(api.app) as client, \
         patch('heatguard.gateway_delivery.urlopen',
               _testclient_urlopen(client, 'gateway-secret')):
        key, inserted = delivery.enqueue('http://testserver/v1/live/ingest', event)
        assert inserted and len(key) == 64
        sent = delivery.deliver_ready()
        assert sent['delivered'] == 1 and sent['failed'] == 0
        assert fleet.repository.count() == 1
        _, inserted_again = delivery.enqueue('http://testserver/v1/live/ingest', event)
        assert inserted_again is False
        assert delivery.outbox.stats() == {'pending': 0, 'sent': 1, 'rejected': 0}


def test_gateway_auth_error_is_visible_and_event_remains_pending(tmp_path: Path):
    delivery = GatewayDelivery(str(tmp_path / 'outbox.sqlite'), api_key='wrong',
                               max_backoff_s=30)
    event = next(simulated_events(devices=1, frames=1, start=T0))
    delivery.enqueue('http://testserver/v1/live/ingest', event)

    def unauthorized(*_args, **_kwargs):
        raise HTTPError('http://testserver', 401, 'Unauthorized', {}, None)

    with patch('heatguard.gateway_delivery.urlopen', unauthorized):
        status = delivery.deliver_ready()
    assert status['failed'] == 1 and status['delivered'] == 0
    assert status['outbox']['pending'] == 1
    assert '401' in status['errors'][0]


def test_gateway_network_retry_and_permanent_rejection_are_explicit(tmp_path: Path):
    event = next(simulated_events(devices=1, frames=1, start=T0))
    retrying = GatewayDelivery(str(tmp_path / 'network.sqlite'), api_key='secret',
                               base_backoff_s=0.1, max_backoff_s=1)
    retrying.enqueue('http://testserver/v1/live/ingest', event)

    with patch('heatguard.gateway_delivery.urlopen',
               side_effect=URLError('connection refused')):
        unavailable = retrying.deliver_ready()
    assert unavailable['failed'] == 1
    assert unavailable['outbox'] == {'pending': 1, 'sent': 0, 'rejected': 0}
    assert 'Fallo de red' in unavailable['errors'][0]

    rejected_event = copy.deepcopy(event)
    rejected_event['event_id'] = 'invalid-permanent-event'
    rejected = GatewayDelivery(str(tmp_path / 'rejected.sqlite'), api_key='secret')
    rejected.enqueue('http://testserver/v1/live/ingest', rejected_event)

    def invalid(*_args, **_kwargs):
        raise HTTPError('http://testserver', 422, 'Unprocessable Entity', {}, None)

    with patch('heatguard.gateway_delivery.urlopen', invalid):
        invalid_status = rejected.deliver_ready()
    assert invalid_status['rejected'] == 1 and invalid_status['failed'] == 0
    assert invalid_status['outbox'] == {'pending': 0, 'sent': 0, 'rejected': 1}
    assert '422' in invalid_status['errors'][0]


def test_resting_overrides_heavy_activity_regression_and_restart(tmp_path: Path):
    db = tmp_path / 'rest.sqlite'
    fleet = FleetService(str(db), scenario=SITE_EXAMPLE)
    events = list(simulated_events(devices=1, frames=2, interval_s=120, start=T0))
    for event in events:
        event['context']['activity_class'] = 'heavy'
        event['context']['work_state'] = 'resting'
        result = fleet.ingest(event, use_scenario=True)
        assert result['accepted']
    timeline = result['result']['exposure_timeline_v22']
    assert timeline['minutes_declared_rest'] == 2
    assert timeline['minutes_declared_work'] == 0
    assert timeline['current_work_state'] == 'resting'
    assert timeline['current_activity_class'] == 'heavy'

    duplicate = fleet.ingest(events[-1], use_scenario=True)
    assert duplicate['duplicate'] and fleet.repository.count() == 2
    restored = FleetService(str(db), scenario=SITE_EXAMPLE)
    snapshot = restored._exposure_v22[('worker_pseudonym', 'virtual-worker-01')].snapshot()
    assert snapshot['minutes_declared_rest'] == 2
    assert snapshot['minutes_declared_work'] == 0


def test_gap_is_unknown_and_late_event_reorders_without_rewind(tmp_path: Path):
    fleet = FleetService(str(tmp_path / 'late.sqlite'), scenario=SITE_EXAMPLE)
    base = list(simulated_events(devices=1, frames=3, interval_s=120, start=T0))
    for event in base:
        event['context'].update(activity_class='heavy', work_state='working')
    assert fleet.ingest(base[0], use_scenario=True)['accepted']
    assert fleet.ingest(base[2], use_scenario=True)['accepted']  # 0 -> 4 min
    late = fleet.ingest(base[1], use_scenario=True)               # insert at 2 min
    timeline = late['result']['exposure_timeline_v22']
    assert timeline['covered_minutes'] == 4
    assert timeline['minutes_declared_work'] == 4
    assert timeline['out_of_order_samples'] == 1
    assert timeline['current_work_state'] == 'working'

    gap = copy.deepcopy(base[2])
    gap['event_id'] = 'after-gap'
    gap['timestamp'] = (T0 + timedelta(minutes=20)).isoformat()
    for observation in gap['observations']:
        observation['timestamp'] = gap['timestamp']
    gap_result = fleet.ingest(gap, use_scenario=True)['result']['exposure_timeline_v22']
    assert gap_result['missing_minutes'] == 16
    assert gap_result['minutes_declared_rest'] == 0


def test_button_long_press_dedup_wrap_reset_and_persistence(tmp_path: Path):
    tracker = ButtonEventTracker('HG-BUTTON-1')
    first = tracker.ingest(struct.pack('<BBH', 1, 2, 1), T0)
    assert len(first) == 1 and first[0]['event_type'] == 'hydration_self_report'
    assert first[0]['self_reported'] and not first[0]['physiological_measurement']
    assert tracker.ingest(struct.pack('<BBH', 0, 2, 1), T0 + timedelta(seconds=1)) == []
    short = tracker.ingest(struct.pack('<BBH', 0, 1, 2), T0 + timedelta(seconds=2))
    assert short[0]['event_type'] == 'button_short_press'

    wrapped = ButtonEventTracker('HG-WRAP', _last_counter=65535)
    wrap_event = wrapped.ingest(struct.pack('<BBH', 1, 2, 0), T0)
    assert len(wrap_event) == 1 and wrap_event[0]['metadata']['counter_wrapped']

    reset = ButtonEventTracker('HG-RESET', _last_counter=100)
    reset_events = reset.ingest(struct.pack('<BBH', 0, 1, 2), T0)
    assert [x['event_type'] for x in reset_events] == ['button_counter_reset', 'button_short_press']

    fleet = FleetService(str(tmp_path / 'events.sqlite'))
    assert fleet.ingest_device_event(first[0])['accepted']
    assert fleet.ingest_device_event(first[0])['duplicate']
    saved = fleet.repository.device_events('HG-BUTTON-1')
    assert len(saved) == 1 and saved[0]['event_type'] == 'hydration_self_report'
    assert fleet.repository.device_event_count(
        'HG-BUTTON-1', event_type='hydration_self_report') == 1
    delivery = GatewayDelivery(str(tmp_path / 'button-outbox.sqlite'))
    delivery.outbox.save_device_state('HG-BUTTON-1', tracker.state())
    restored_tracker = ButtonEventTracker.from_state(
        'HG-BUTTON-1', delivery.outbox.load_device_state('HG-BUTTON-1'))
    assert restored_tracker.ingest(struct.pack('<BBH', 0, 1, 2),
                                   T0 + timedelta(seconds=3)) == []


def test_real_firmware_binary_contract_and_manual_actuators():
    assert BUTTON_UUID.endswith('0007-4865-6174-4775-617264436c70')
    assert MOTOR_UUID.endswith('0006-4865-6174-4775-617264436c70')
    assert decode_button_notification(b'\x01\x02\x34\x12')['counter'] == 0x1234
    assert encode_led_command(1, 2, 255) == b'\x01\x02\xff'
    assert encode_motor_command(200, 4) == b'\xc8\x04'
    with pytest.raises(ValueError):
        decode_button_notification(b'\x01\x02')
    with pytest.raises(ValueError):
        encode_led_command(0, 0, 256)


def test_device_event_authenticated_api_and_panel_payload(tmp_path: Path):
    fleet = FleetService(str(tmp_path / 'api-events.sqlite'), scenario=SITE_EXAMPLE)
    telemetry = next(simulated_events(devices=1, frames=1, start=T0))
    fleet.ingest(telemetry, use_scenario=True)
    button_event = ButtonEventTracker(telemetry['device_id']).ingest(
        struct.pack('<BBH', 1, 2, 1), T0)[0]
    with patch.object(api, '_fleet', fleet), \
         patch.dict('os.environ', {'HG_ADMIN_API_KEY': 'admin', 'HG_VIEWER_API_KEY': 'view'}):
        client = TestClient(api.app)
        assert client.post('/v1/fleet/device-events', json=button_event).status_code == 401
        accepted = client.post('/v1/fleet/device-events', json=button_event,
                               headers={'X-API-Key': 'admin'})
        assert accepted.status_code == 200 and accepted.json()['accepted']
        duplicate = client.post('/v1/fleet/device-events', json=button_event,
                                headers={'X-API-Key': 'admin'}).json()
        assert duplicate['duplicate']
        panel = client.get('/v1/mvp/devices', headers={'X-API-Key': 'view'}).json()['devices'][0]
        assert panel['hydration_self_report_count'] == 1
        assert panel['last_hydration_self_report']['physiological_measurement'] is False
        events = client.get(f"/v1/fleet/devices/{telemetry['device_id']}/events",
                            headers={'X-API-Key': 'view'}).json()['events']
        assert len(events) == 1


def test_radiation_sources_preserve_kind_age_and_uncertainty():
    event = next(simulated_events(devices=1, frames=1, start=T0))
    event['context']['radiation'] = {
        'mode': 'instrumental', 'solar_w_m2': 712, 'source_id': 'PYR-REF-01',
        'calibration_id': 'CAL-2026-11', 'uncertainty_w_m2': 18,
        'observed_at': (T0 - timedelta(minutes=3)).isoformat(),
    }
    prepared, info = prepare_radiation(event)
    solar = [x for x in prepared['observations'] if x['parameter'] == 'solar_w_m2'][0]
    assert solar['kind'] == 'measured' and solar['source'] == 'PYR-REF-01'
    assert solar['metadata']['uncertainty_w_m2'] == 18
    assert solar['timestamp'] == (T0 - timedelta(minutes=3)).isoformat()
    assert info['calibrated_radiometer'] is True

    manual = copy.deepcopy(event)
    manual['context']['radiation'] = {'mode': 'manual', 'solar_w_m2': 500,
                                      'uncertainty_w_m2': 150}
    manual_prepared, manual_info = prepare_radiation(manual)
    item = [x for x in manual_prepared['observations'] if x['parameter'] == 'solar_w_m2'][0]
    assert item['kind'] == 'assumed' and item['metadata']['not_measured']
    assert manual_info['source_kind'] == 'assumed'


def test_panel_contains_integrated_v031_fields():
    html = Path(api.__file__).with_name('static').joinpath('mvp.html').read_text(encoding='utf-8')
    assert 'v0.31 STABLE' in html
    assert 'hidrataciones autodeclaradas' in html
    assert 'minutes_declared_rest' in html
    assert '/events?limit=100' in html
    assert 'no es una medición fisiológica' in html
