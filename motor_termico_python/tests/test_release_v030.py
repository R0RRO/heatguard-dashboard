from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from heatguard.exposure_v22 import DeviceExposureV22
from heatguard.fleet import FleetService
from heatguard.fusion import select_inputs
from heatguard.occupational_context import evaluate_occupational_context
from heatguard.review_engine import ExperimentalReviewEngine
from heatguard.schema import Observation
from heatguard.virtual_site import SITE_EXAMPLE, simulated_events


T0 = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


def _estimate(value=29.0):
    return {'status': 'computed', 'value_c': value}


def _band(low=28.0, high=30.0, threshold=28.0):
    return {'status': 'entire_assumed_band_above_threshold', 'attention': 'priority_review',
            'band_lower_c': low, 'band_upper_c': high, 'threshold_c': threshold,
            'duration_review_min': 2, 'hysteresis_c': .5,
            'repeat_suppression_min': 30, 'minimum_coverage_fraction': 0}


def test_observation_quality_and_contradiction_are_traceable():
    a = Observation.from_dict({'parameter':'air_temperature_c','value':30,'unit':'degC',
        'kind':'measured','source':'clip','quality':'good','timestamp':T0.isoformat()})
    b = Observation.from_dict({'parameter':'air_temperature_c','value':34,'unit':'degC',
        'kind':'external','source':'station','timestamp':T0.isoformat()})
    fusion = select_inputs([a,b], T0.isoformat(), 'z1')
    assert fusion.chosen['air_temperature_c'].source == 'clip'
    assert fusion.contradictions[0]['spread'] == 4
    assert a.as_dict()['quality'] == 'good'
    with pytest.raises(ValueError, match='quality'):
        Observation.from_dict({'parameter':'air_temperature_c','value':30,'unit':'degC',
            'kind':'measured','source':'clip','quality':'perfect'})


def test_exposure_has_15_30_60_and_configurable_shift():
    state = DeviceExposureV22()
    for minute in range(0, 7):
        state.update((T0+timedelta(minutes=minute)).isoformat(), _estimate(), _band(),
                     activity='heavy', zone_id='sun', shift_duration_hours=10)
    out = state.snapshot(T0+timedelta(minutes=6))
    assert set(out['rolling_windows']) == {'15m','30m','60m'}
    assert out['covered_minutes'] == 6
    assert out['rolling_shift']['window_minutes'] == 600
    assert out['current_zone_id'] == 'sun'
    assert out['current_zone_duration_minutes'] == 6


def test_review_engine_persistence_and_repeat_suppression():
    engine = ExperimentalReviewEngine()
    quality = {'flag_codes': []}
    early = {'minutes_entire_band_ge_research_threshold': 1,
             'minutes_possible_ge_research_threshold': 1,
             'coverage_of_window_fraction': .5, 'observed_span_minutes': 2}
    assert engine.update('worker:x', T0.isoformat(), _band(), early, quality)['state'] == 'monitoring_persistence'
    mature = dict(early, minutes_entire_band_ge_research_threshold=3,
                  minutes_possible_ge_research_threshold=3)
    first = engine.update('worker:x', (T0+timedelta(minutes=3)).isoformat(), _band(), mature, quality)
    second = engine.update('worker:x', (T0+timedelta(minutes=4)).isoformat(), _band(), mature, quality)
    assert first['state'] == 'priority_review' and first['review_event_emitted']
    assert second['state'] == 'priority_review' and second['repeat_suppressed']
    assert not second['automatic_actuator_command']


def test_occupational_context_stays_independent_from_steps():
    context = {'activity_class':'heavy','activity_source':'supervisor',
               'metabolic_rate_w':450,'metabolic_rate_source':'task_observation',
               'clothing':{'ensemble':'double_layer','adjustment_c':3,'source':'NIOSH_2016_example'},
               'acclimatization':'in_progress','work_state':'working'}
    out = evaluate_occupational_context(context, _estimate(28))
    assert out['clothing_adjusted_research_value_c'] == 31
    assert out['metabolic_rate_inferred_from_steps'] is False
    assert out['normative_assessment_performed'] is False


def test_shift_exposure_restores_across_restart(tmp_path: Path):
    db = tmp_path/'shift.sqlite'
    first = FleetService(str(db), scenario=SITE_EXAMPLE)
    events = list(simulated_events(devices=1, frames=4, interval_s=120, start=T0))
    for event in events:
        event['context']['worker_id'] = 'worker-pseudonym-1'
        event['context']['research_review'] = {'enabled':True,'threshold_c':28,
            'illustrative_half_width_c':1.5,'duration_review_min':2,'origin':'test'}
        assert first.ingest(event, use_scenario=True)['accepted']
    restored = FleetService(str(db), scenario=SITE_EXAMPLE)
    latest = restored.latest(events[-1]['device_id'])['result']['exposure_timeline_v22']
    # Stored result proves the pre-restart state; restored state is exercised by
    # adding one more sample and must continue rather than reset.
    follow = list(simulated_events(devices=1, frames=1, start=T0+timedelta(minutes=8)))[0]
    follow['event_id'] = 'after-restart'
    follow['context'].update(events[-1]['context'])
    result = restored.ingest(follow, use_scenario=True)['result']['exposure_timeline_v22']
    assert latest['covered_minutes'] == 6
    assert result['covered_minutes'] == 8  # 2-minute communication gap is covered
    assert result['subject_type'] == 'worker_pseudonym'


def test_viewer_cannot_generate_demo_and_csv_export_uses_real_backend(tmp_path: Path):
    from heatguard import api
    fleet = FleetService(str(tmp_path/'api.sqlite'), scenario=SITE_EXAMPLE)
    event = next(simulated_events(devices=1,frames=1,start=T0))
    fleet.ingest(event,use_scenario=True)
    with patch.object(api,'_fleet',fleet), patch.dict('os.environ',{
            'HG_VIEWER_API_KEY':'viewer','HG_ADMIN_API_KEY':'admin','HG_ENABLE_DEMO':'1'}, clear=False):
        client = TestClient(api.app)
        assert client.get('/v1/fleet',headers={'X-API-Key':'viewer'}).status_code == 200
        assert client.post('/v1/mvp/demo',headers={'X-API-Key':'viewer'}).status_code == 403
        response = client.get(f"/v1/fleet/devices/{event['device_id']}/export.csv",
                              headers={'X-API-Key':'viewer'})
        assert response.status_code == 200
        assert 'wbgt_status' in response.text
