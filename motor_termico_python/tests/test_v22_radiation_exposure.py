"""Pruebas v0.22: no hay WBGT inventado, bandas experimentales ni dosis falsas."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import tempfile
import pytest
from fastapi.testclient import TestClient

from heatguard.radiation_v22 import prepare_radiation
from heatguard.decision_support_v22 import evaluate_band
from heatguard.exposure_v22 import DeviceExposureV22
from heatguard.fleet import FleetService
from heatguard.virtual_site import SITE_EXAMPLE
from heatguard.pipeline import evaluate

T0=datetime(2026,11,15,12,0,tzinfo=timezone.utc)

def ev(dt=0, solar=False, policy=True):
    observations=[
        {'parameter':'air_temperature_c','unit':'degC','value':31.5,'kind':'measured','source':'sensor_demonstration'},
        {'parameter':'relative_humidity_pct','unit':'percent','value':60,'kind':'measured','source':'sensor_demonstration'},
        {'parameter':'wind_speed_m_s','unit':'m/s','value':1,'kind':'external','source':'example_wind'},
        {'parameter':'battery_level_pct','unit':'percent','value':80,'kind':'measured','source':'demo'},
        {'parameter':'steps_since_boot','unit':'count','value':10+dt,'kind':'measured','source':'demo'},
        {'parameter':'hydration_self_report_count','unit':'count','value':1,'kind':'estimated','source':'manual_self_report'},
    ]
    if solar:observations.append({'parameter':'solar_w_m2','unit':'W/m2','value':400,'kind':'external','source':'regional_weather'})
    return {'event_id':str(dt), 'device_id':'HG-SAMPLE', 'timestamp':(T0+timedelta(seconds=dt)).isoformat(),
        'context':{'zone_id':'z','environment':'outdoor','activity_class':'moderate',
            **({'research_review':{'enabled':True,'threshold_c':28,'illustrative_half_width_c':1.5,'duration_review_min':5}} if policy else {})},
        'observations':observations, 'transport_metadata':{'simulated':True}}


def test_manual_radiation_assumed_and_no_overwrite():
    p=ev();p['context']['radiation']={'mode':'manual','solar_w_m2':650}
    out,meta=prepare_radiation(p)
    assert meta['solar_added']
    assert next(o for o in out['observations'] if o['parameter']=='solar_w_m2')['kind']=='assumed'
    assert 'solar_w_m2' not in {o['parameter'] for o in p['observations']}
    p=ev(solar=True);p['context']['radiation']={'mode':'manual','solar_w_m2':650}
    out,meta=prepare_radiation(p)
    assert not meta['solar_added']
    assert len([o for o in out['observations'] if o['parameter']=='solar_w_m2'])==1
    assert next(o for o in out['observations'] if o['parameter']=='solar_w_m2')['value']==400


def test_visual_label_never_invents_irradiance():
    e=ev(); e['context']['radiation']={'mode':'visual_label','scene_label':'shade'}
    r=evaluate(e)
    assert r['environmental_estimator_v18']['status']=='missing_inputs'
    assert r['radiative_context_v22']['status']=='categorical_only'
    assert not r['radiative_context_v22']['solar_added']


def test_differential_does_not_generate_watts_or_wbgt():
    e=ev();e['context']['radiation']={'mode':'differential','black_surface_c':42,'white_surface_c':32,'source_kind':'assumed'}
    r=evaluate(e)
    assert r['environmental_estimator_v18']['status']=='missing_inputs'
    assert r['inputs_selected']['radiative_delta_c']['value']==10
    assert r['radiative_context_v22']['calibrated_radiometer'] is False


def test_components_solar_scenario():
    e=ev();e['context']['radiation']={'mode':'solar_components','direct_horizontal_w_m2':600,'diffuse_horizontal_w_m2':100,'direct_exposure_fraction':0.25}
    r=evaluate(e)
    assert r['inputs_selected']['solar_w_m2']['value']==250
    assert r['inputs_selected']['solar_w_m2']['kind']=='estimated'
    assert r['environmental_estimator_v18']['status']=='computed'


def test_band_crossing_no_certification_and_missing():
    context={'research_review':{'enabled':True,'threshold_c':28,'illustrative_half_width_c':1.5}}
    r=evaluate_band({'status':'computed','value_c':27.5},context)
    assert r['status']=='assumed_band_intersects_threshold'
    assert not r['safety_alert_enabled'] and r['not_confidence_interval']
    assert evaluate_band({'status':'computed','value_c':31},context)['attention']=='priority_review'
    assert evaluate_band({'status':'computed','value_c':25},context)['attention']=='monitor_inputs_not_safety_clearance'
    assert evaluate_band({'status':'missing_inputs'},context)['status']=='missing_estimate'
    assert evaluate_band({'status':'computed','value_c':29},{})['status']=='not_configured'


def test_bad_config_rejected():
    with pytest.raises(ValueError):evaluate_band({'status':'computed','value_c':30},{'research_review':{'enabled':True,'threshold_c':28,'illustrative_half_width_c':-1}})
    with pytest.raises(ValueError):prepare_radiation({**ev(),'context':{**ev()['context'],'radiation':{'mode':'visual_label','scene_label':'detected_irradiance_800'}}})


def test_exposure_exact_intervals_and_gap():
    t=DeviceExposureV22()
    wb={'status':'computed','value_c':29}
    band=evaluate_band(wb, {'research_review':{'enabled':True,'threshold_c':28,'illustrative_half_width_c':1.5}})
    t.update(T0.isoformat(),wb,band,activity='moderate')
    s=t.update((T0+timedelta(minutes=2)).isoformat(),wb,band,activity='resting')
    assert s['covered_minutes']==2
    assert s['minutes_possible_ge_research_threshold']==2
    assert s['minutes_entire_band_ge_research_threshold']==0
    assert s['minutes_declared_work']==2
    s=t.update((T0+timedelta(minutes=15)).isoformat(),wb,band)
    assert s['covered_minutes']==2
    assert s['missing_minutes']==13
    assert s['coverage_of_full_hour_fraction']<0.04
    assert s['not_iso_7243_twa']
    back=t.update((T0+timedelta(minutes=5)).isoformat(),wb,band)
    assert back['out_of_order_samples']==1
    assert t.last_timestamp==T0+timedelta(minutes=15)


def test_missing_wbgt_not_counted_as_coverage():
    t=DeviceExposureV22()
    t.update(T0.isoformat(),{'status':'missing_inputs'}, {})
    out=t.update((T0+timedelta(minutes=2)).isoformat(),{'status':'missing_inputs'}, {})
    assert out['missing_minutes']==2 and out['covered_minutes']==0


def test_fleet_integration_and_restore(tmp_path):
    db=tmp_path/'runtime.sqlite'
    f=FleetService(str(db),scenario=SITE_EXAMPLE)
    e=ev(0);e['context']['radiation']={'mode':'manual','solar_w_m2':650}
    a=f.ingest(e)
    assert a['accepted'] and a['result']['decision_support_v22']['status']!='not_configured'
    e2=ev(120);e2['context']['radiation']={'mode':'manual','solar_w_m2':650}
    b=f.ingest(e2)
    assert b['accepted']
    assert b['result']['exposure_timeline_v22']['covered_minutes']==2
    assert b['result']['inputs_selected']['battery_level_pct']['value']==80
    f2=FleetService(str(db),scenario=SITE_EXAMPLE)
    summary=f2.fleet_summary()['devices'][0]
    assert summary['exposure_timeline_v22']['covered_minutes']==2
    assert summary['steps_since_boot']==130
    assert not f2.fleet_summary()['safety_alerts_enabled']


def test_api_mvp_includes_timeline_and_no_operational_alert(tmp_path):
    from heatguard import api
    f=FleetService(str(tmp_path/'a.sqlite'),scenario=SITE_EXAMPLE)
    with patch.object(api,'_fleet',f),patch.dict('os.environ',{'HG_ENABLE_DEMO':'1','HG_API_KEY':''}):
        c=TestClient(api.app)
        r=c.post('/v1/mvp/demo?devices=3&frames=8')
        assert r.status_code==200,r.text
        assert r.json()['accepted']==24
        data=c.get('/v1/mvp/devices').json()
        assert data['count']==3
        assert all(x['radiative_delta_c'] is not None for x in data['devices'])
        assert all(x['exposure_timeline']['covered_minutes']==7 for x in data['devices'] if x['estimated_wbgt']['status']=='computed')
        assert data['safety_alerts_enabled'] is False


def test_worker_pseudonym_accumulates_across_devices(tmp_path):
    f=FleetService(str(tmp_path/'swap.sqlite'))
    a=ev(0,solar=True);a['context']['worker_id']='pseudo-worker-12'
    a['device_id']='CLIP-1';f.ingest(a)
    b=ev(120,solar=True);b['context']['worker_id']='pseudo-worker-12'
    b['device_id']='CLIP-2'
    r=f.ingest(b)
    assert r['result']['exposure_timeline_v22']['covered_minutes']==2
    assert r['result']['exposure_timeline_v22']['subject_type']=='worker_pseudonym'
    restart=FleetService(str(tmp_path/'swap.sqlite'))
    assert restart._exposure_v22[('worker_pseudonym','pseudo-worker-12')].snapshot()['covered_minutes']==2
