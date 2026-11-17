"""Pruebas v0.18: completar vs no completar meteorología, procedencia y flujo HTTP."""
from __future__ import annotations

import copy
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from heatguard.environmental_v18 import environmental_estimate
from heatguard.fusion import select_inputs
from heatguard.pipeline import evaluate
from heatguard.schema import Observation
from heatguard.virtual_site import SITE_EXAMPLE
from heatguard.fleet import FleetService

TSTAMP = '2026-11-14T18:00:00Z'
CTX = {'zone_id':'obra-demo', 'environment':'outdoor',
       'location': {'latitude_deg':-33.45,'longitude_deg':-70.66,'utc_offset_hours':-3},
       'weather_model':{'wind_height_m':10, 'averaging_minutes':60,
                        'urban':1,'vertical_temperature_difference_c':0}}

def obs(key, val, unit, kind='assumed', source='PRUEBA_FICTICIA',stamp=TSTAMP):
    return {'parameter':key,'value':val,'unit':unit,'kind':kind,
            'source':source,'timestamp':stamp}

def event(full=True):
    readings=[obs('air_temperature_c',31,'degC'),obs('relative_humidity_pct',65,'percent')]
    if full:
        readings += [obs('solar_w_m2',620,'W/m2'),obs('wind_speed_m_s',2,'m/s'),
                     obs('pressure_hpa',1010,'hPa')]
    return {'device_id':'HG-VIRT','timestamp':TSTAMP,'context':copy.deepcopy(CTX),
            'transport_metadata':{'simulated':True},'observations':readings}


def test_no_wbgt_without_solar_and_wind():
    r = evaluate(event(full=False))
    assert r['environmental_estimator_v18']['status']=='missing_inputs'
    assert set(r['environmental_estimator_v18']['missing']) == {'solar_w_m2','wind_speed_m_s'}
    assert 'heat_index_c' in r['metrics']
    assert r['environmental_estimator_v18']['alerts_enabled'] is False


def test_ono_reproduces_existing_implementation():
    from heatguard.ono_v09 import wbgt_ono
    r = evaluate(event())['environmental_estimator_v18']
    assert r['status']=='computed'
    assert r['value_c'] == round(wbgt_ono(31,65,620,2),3)
    assert r['input_quality']['category']=='scenario_only'
    assert r['not_iso_7243_measurement'] is True
    assert r['sun_shade_sensitivity']['status']=='hypothetical_sensitivity_not_confidence_interval'
    assert any('virtual' in w.lower() for w in r['warnings'])


def test_indoor_blocks_model_even_with_weather():
    p=event();p['context']['environment']='indoor'
    r=evaluate(p)['environmental_estimator_v18']
    assert r['status']=='not_applicable'
    assert 'value_c' not in r


def test_measured_local_overrides_external_but_no_false_certification():
    p=event()
    p['transport_metadata']['simulated']=False
    # otra lectura de misma variable, un modelo regional no reemplaza sensor local
    p['observations'].append(obs('air_temperature_c',29,'degC','external','OPEN_METEO_HOURLY_MODEL'))
    p['observations'][0]['kind']='measured'
    p['observations'][0]['source']='REAL_UNVALIDATED_SENSOR'
    for k in ('solar_w_m2','wind_speed_m_s'):
        item=next(x for x in p['observations'] if x['parameter']==k)
        item['kind']='external';item['source']='OPEN_METEO_HOURLY_MODEL'
    r=evaluate(p)['environmental_estimator_v18']
    assert r['status']=='computed'
    assert r['provenance']['air_temperature_c']['source']=='REAL_UNVALIDATED_SENSOR'
    assert r['input_quality']['category']=='scenario_only'  # RH es una hipótesis
    assert r['input_quality']['no_occupational_safety_certification'] is True


def test_external_and_measured_quality():
    p=event()
    p['transport_metadata']['simulated']=False
    for item in p['observations']:
        item['kind']='measured' if item['parameter'] in ('air_temperature_c','relative_humidity_pct') else 'external'
        item['source']='HTU21D_REPORTADO' if item['kind']=='measured' else 'OPEN_METEO_HOURLY_MODEL'
    r=evaluate(p)['environmental_estimator_v18']
    assert r['input_quality']['category']=='mixed_local_and_external'
    assert r['provenance']['wind_speed_m_s']['kind']=='external'
    assert any('carcasa' in w for w in r['warnings'])


def test_stale_weather_rejected():
    p=event()
    for item in p['observations']:
        if item['parameter']=='solar_w_m2':
            item['kind']='external'
            item['timestamp']='2026-11-14T15:00:00Z'
    r=evaluate(p)
    assert 'solar_w_m2' in r['environmental_estimator_v18']['missing']
    assert r['environmental_estimator_v18']['status']=='missing_inputs'


def test_no_unreported_wind_substitution_and_bad_metadata():
    p=event();p['observations']=[o for o in p['observations'] if o['parameter']!='wind_speed_m_s']
    assert evaluate(p)['environmental_estimator_v18']['status']=='missing_inputs'
    p['transport_metadata']=['bad']
    with pytest.raises(ValueError,match='transport_metadata'):
        evaluate(p)


def test_ble_simulated_packets_marked_simulated():
    from heatguard.virtual_site import simulated_events
    e=next(simulated_events(devices=1,frames=1,start=datetime(2026,11,14,tzinfo=timezone.utc)))
    assert e['transport_metadata']['simulated'] is True
    assert all(o['kind']=='assumed' for o in e['observations'])


def test_http_dashboard_demo_and_no_access_without_flag():
    from heatguard import api
    with tempfile.TemporaryDirectory() as tmp:
        db=FleetService(str(Path(tmp)/'runtime.sqlite'),scenario=SITE_EXAMPLE)
        with patch.object(api,'_fleet',db),patch.dict(os.environ,{'HG_ENABLE_DEMO':'0','HG_API_KEY':''}):
            cli=TestClient(api.app)
            assert cli.get('/mvp').status_code==200
            assert 'HeatGuard' in cli.get('/mvp').text
            assert cli.post('/v1/mvp/demo').status_code==403
            assert cli.get('/v1/mvp/devices').json()['count']==0
            with patch.dict(os.environ,{'HG_ENABLE_DEMO':'1'}):
                r=cli.post('/v1/mvp/demo?devices=3&frames=1')
                assert r.status_code==200,r.text
                assert r.json()['accepted']==3
                again=cli.post('/v1/mvp/demo?devices=3&frames=1')
                assert again.json()['accepted']==3  # ID de demo único
                data=cli.get('/v1/mvp/devices').json()
                assert data['count']==3
                assert all(x['simulated'] for x in data['devices'])
                outdoor=next(x for x in data['devices'] if x['environment']=='outdoor')
                assert outdoor['estimated_wbgt']['status']=='computed'
                assert outdoor['estimated_wbgt']['input_quality']['category']=='scenario_only'
                indoor=next(x for x in data['devices'] if x['environment']=='indoor')
                assert indoor['estimated_wbgt']['status']=='not_applicable'
                assert data['safety_alerts_enabled'] is False


def test_api_key_applies_to_mvp():
    from heatguard import api
    with patch.dict(os.environ,{'HG_API_KEY':'test-123','HG_ENABLE_DEMO':'1'}):
        cli=TestClient(api.app)
        assert cli.get('/v1/mvp/devices').status_code==401
        assert cli.post('/v1/mvp/demo').status_code==401
        assert cli.get('/v1/mvp/devices',headers={'X-API-Key':'test-123'}).status_code==200
