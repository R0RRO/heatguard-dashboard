"""v0.19: detección de calidad y recorrido GATT binario -> estimador -> SQLite."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from heatguard.lab_acceptance_v19 import run_lab, _gatt_packets, _simulated
from heatguard.ble_existing import ExistingClipAssembler, HUM_UUID, TEMP_UUID, decode_notification
from heatguard.telemetry_quality_v19 import EngineeringTelemetryMonitor
from heatguard.pipeline import evaluate
from heatguard.virtual_site import SITE_EXAMPLE
from heatguard.fleet import FleetService

T0 = datetime(2026, 11, 14, 17, 0, tzinfo=timezone.utc)


def test_gatt_binary_fixture_is_the_real_declared_packet_format():
    packets = _gatt_packets(1, 'variation')
    decoded = {}
    for uuid, data in packets:
        decoded.update(decode_notification(uuid, data))
    assert decoded['air_temperature_c'] == pytest.approx(30.36)
    assert decoded['relative_humidity_pct'] == pytest.approx(55.87)
    assert decoded['steps_since_boot'] == 4
    assert decoded['battery_level_pct'] == 91


def test_assembler_does_not_emit_unpaired_temperature():
    a = ExistingClipAssembler('HG-TEST', 'test', 'outdoor')
    assert a.ingest(TEMP_UUID, b'\xa4\x0b', T0) is None
    assert a.ingest(HUM_UUID, b'\x94\x15', T0 + timedelta(seconds=8)) is None


def test_mislabeled_simulation_never_pretends_to_be_measured():
    a = ExistingClipAssembler('HG-TEST', 'test', 'outdoor')
    e = None
    for uuid, raw in _gatt_packets(0, 'variation'):
        e = a.ingest(uuid, raw, T0) or e
    e = _simulated(e, 'test-01')
    assert all(o['kind'] == 'assumed' for o in e['observations'])
    assert evaluate(e)['environmental_estimator_v18']['status'] == 'missing_inputs'
    quality = EngineeringTelemetryMonitor().inspect(e, evaluate(e))
    assert quality['status'] == 'incomplete_for_outdoor_wbgt'
    assert 'SIMULATED' in quality['flag_codes']


def test_qa_abrupt_change_is_not_occupational_alert():
    monitor = EngineeringTelemetryMonitor()
    def ev(value: float, time: datetime):
        e = {'device_id': 'X', 'timestamp': time.isoformat(), 'context': {'zone_id': 'a','environment':'outdoor'},
             'transport_metadata': {'simulated':True}, 'observations': [
             {'parameter':'air_temperature_c','value':value,'unit':'degC','kind':'assumed','source':'virtual'},
             {'parameter':'relative_humidity_pct','value':50,'unit':'percent','kind':'assumed','source':'virtual'}]}
        return e
    a = ev(30, T0)
    b = ev(36, T0 + timedelta(seconds=30))
    monitor.inspect(a, evaluate(a))
    result = monitor.inspect(b, evaluate(b))
    assert 'ABRUPT_T_CHANGE' in result['flag_codes']
    assert result['status'] == 'review_data'
    assert result['occupational_alerts_enabled'] is False


def test_nonmonotonic_time_does_not_overwrite_quality_baseline():
    monitor = EngineeringTelemetryMonitor()
    def pair(ts):
        e={'device_id':'X','timestamp':ts.isoformat(), 'transport_metadata':{'simulated':True}}
        r={'inputs_selected':{'air_temperature_c':{'value':29,'kind':'assumed','source':'sim'},'relative_humidity_pct':{'value':65,'kind':'assumed','source':'sim'}},
           'environmental_estimator_v18':{'status':'missing_inputs','missing':['solar_w_m2']}}
        return e,r
    a,r=pair(T0);monitor.inspect(a,r)
    b,r=pair(T0-timedelta(seconds=5))
    assert 'NON_MONOTONIC_TIMESTAMP' in monitor.inspect(b,r)['flag_codes']
    assert monitor._state['X'].timestamp == T0


def test_lab_four_scenarios_and_8_assertions(tmp_path):
    r=run_lab(out=tmp_path/'out', db=tmp_path/'lab.sqlite',frames=8,start=T0,run_id='unit')
    assert r['status']=='passed'
    assert r['accepted_events']==32
    assert r['gatt_notifications']==128
    assert len(r['checks'])==8
    assert all(c['passed'] for c in r['checks'])
    report=json.loads((tmp_path/'out'/'ACCEPTANCE_REPORT.json').read_text(encoding='utf-8'))
    assert report['physical_hardware_used'] is False
    rows=[json.loads(row) for row in (tmp_path/'out'/'results.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(rows)==32
    assert any('POSSIBLE_FLATLINE' in row['engineering_quality_v19']['flag_codes'] for row in rows)
    assert all(row['engineering_quality_v19']['validated_occupational_wbgt'] is False for row in rows)


def test_original_ble_live_ingest_has_quality_and_no_operational_alert(tmp_path):
    from heatguard import api
    from unittest.mock import patch
    db = FleetService(str(tmp_path/'for-api.sqlite'),scenario=SITE_EXAMPLE)
    run_lab(out=tmp_path/'run',db=tmp_path/'for-api.sqlite',start=T0,run_id='api')
    with patch.object(api, '_fleet', db):
        c=TestClient(api.app)
        response=c.get('/v1/mvp/devices')
        assert response.status_code==200
        assert response.json()['count']==4
        assert all('engineering_quality' in x for x in response.json()['devices'])
        assert all(not x['occupational_alerts_enabled'] for x in response.json()['devices'])
        assert 'Calidad de telemetría' in c.get('/mvp').text


def test_duplicate_packets_not_accumulated(tmp_path):
    from heatguard.virtual_site import simulated_events
    fl=FleetService(str(tmp_path/'dup.sqlite'),scenario=SITE_EXAMPLE)
    e=next(simulated_events(devices=1,frames=1,start=T0))
    first=fl.ingest(e,use_scenario=True)
    second=fl.ingest(e,use_scenario=True)
    assert first['accepted'] is True
    assert second['duplicate'] is True
    assert fl.repository.count()==1
