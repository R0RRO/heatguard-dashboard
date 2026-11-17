import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from heatguard.virtual_site import simulated_events
from heatguard.context_estimation import relative_airflow_scenario


class TestApiV04(unittest.TestCase):
    def test_flow_http_demo_to_fleet(self):
        from heatguard import api
        with tempfile.TemporaryDirectory() as td:
            from heatguard.fleet import FleetService
            from heatguard.live import LiveStore
            with patch.object(api, '_fleet', FleetService(str(Path(td) / 'api.sqlite'))), \
                 patch.object(api, 'live_store', LiveStore()), \
                 patch.dict(os.environ, {'HG_ENABLE_DEMO':'1'}):
                c = TestClient(api.app)
                self.assertEqual(c.get('/health').status_code, 200)
                demo = c.post('/v1/demo/generate?devices=3&frames=3&scenario=true')
                self.assertEqual(demo.status_code, 200, demo.text)
                self.assertEqual(demo.json()['accepted'], 9)
                fleet = c.get('/v1/fleet').json()
                self.assertEqual(fleet['device_count'], 3)
                self.assertEqual(fleet['stored_events'], 9)
                self.assertEqual(len(c.get('/v1/live/devices').json()['devices']), 3)
                self.assertEqual(len(c.get('/v1/fleet/zones').json()['zones']), 3)
                self.assertEqual(c.get('/v1/fleet/devices/HG-0101/history').status_code, 200)
                self.assertFalse(fleet['safety_alerts_enabled'])

    def test_api_key_optional_policy(self):
        from heatguard import api
        with patch.dict(os.environ, {'HG_API_KEY':'test-not-for-production'}):
            c=TestClient(api.app)
            self.assertEqual(c.get('/v1/fleet').status_code, 401)
            self.assertEqual(c.get('/v1/fleet', headers={'X-API-Key':'test-not-for-production'}).status_code, 200)

    def test_future_gateway_explicit_consent(self):
        from heatguard import api
        with tempfile.TemporaryDirectory() as td:
            from heatguard.fleet import FleetService
            e=next(simulated_events(devices=1,frames=1,
                   start=datetime(2026,11,11,20,0,tzinfo=timezone.utc)))
            with patch.object(api,'_fleet',FleetService(str(Path(td)/'api.sqlite'))):
                c=TestClient(api.app)
                p={'event':e,'phone':{'location_consent': True, 'latitude_deg':-33.44,
                                     'longitude_deg':-70.62,'speed_m_s':1.25},
                   'wearable':{'physiology_consent':True,'heart_rate_bpm':90}}
                r=c.post('/v1/gateway/mobile',json=p)
                self.assertEqual(r.status_code,200,r.text)
                self.assertTrue(r.json()['accepted'])
                sources=r.json()['result']['inputs_selected']
                self.assertEqual(sources['heart_rate_bpm']['source'],'OPTIONAL_WEARABLE_NOT_DIAGNOSTIC')

    def test_airflow_illustrative_only(self):
        result=relative_airflow_scenario({
            'wind_speed_m_s':{'value':2,'source':'MODEL'},
            'gps_speed_m_s':{'value':1.5,'source':'PHONE'},
        })
        self.assertEqual(result['minimum_m_s'],0.5)
        self.assertEqual(result['maximum_m_s'],3.5)
        self.assertFalse(result['used_in_wbgt'])


if __name__=='__main__': unittest.main()
