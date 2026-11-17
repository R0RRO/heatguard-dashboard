"""Pruebas sin dispositivo; algunas usan datos sintéticos etiquetados explícitamente."""
import copy
import csv
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from heatguard.fleet import FleetService
from heatguard.gateway import append_gateway_sources
from heatguard.neighbors import neighbor_candidates
from heatguard.exposure import ExposureState
from heatguard.scenarios import SiteScenario, apply_explicit_scenario
from heatguard.schema import read_event
from heatguard.virtual_site import SITE_EXAMPLE, simulated_events


class TestOfflineBackend(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'heatguard.sqlite')
        self.first = next(simulated_events(devices=3, frames=1,
                                           start=datetime(2026, 11, 11, 20, 0, tzinfo=timezone.utc)))

    def tearDown(self):
        self.tmp.cleanup()

    def test_virtual_gatt_compatible_and_software_only(self):
        a = list(simulated_events(devices=3, frames=3))
        self.assertEqual(len(a), 9)
        self.assertEqual(len({x['device_id'] for x in a}), 3)
        self.assertTrue(all(x['transport_metadata']['simulated'] for x in a))
        self.assertTrue(all(o['kind'] == 'assumed' for e in a for o in e['observations']))

    def test_explicit_scenario_opt_in(self):
        plain = apply_explicit_scenario(self.first, SITE_EXAMPLE)
        self.assertEqual(plain, self.first)
        enabled = apply_explicit_scenario(self.first, SITE_EXAMPLE, enabled=True)
        param = {r['parameter']: r for r in enabled['observations']}
        self.assertEqual(param['solar_w_m2']['kind'], 'assumed')
        self.assertEqual(param['wind_speed_m_s']['source'], 'EXPLICIT_SCENARIO_NOT_SENSOR')
        self.assertNotIn('solar_w_m2', [r['parameter'] for r in self.first['observations']])

    def test_assumptions_never_override_existing_sensor(self):
        e = copy.deepcopy(self.first)
        e['observations'].append({'parameter':'wind_speed_m_s','value':2.3,'unit':'m/s',
                                  'kind':'measured','source':'EXPERIMENTAL_ANEMOMETER'})
        result = apply_explicit_scenario(e, SITE_EXAMPLE, enabled=True)
        self.assertEqual([x['value'] for x in result['observations'] if x['parameter']=='wind_speed_m_s'], [2.3])

    def test_scenario_indoor_does_not_add_solar(self):
        e = copy.deepcopy(self.first)
        e['context']['environment'] = 'indoor'
        result = apply_explicit_scenario(e, SITE_EXAMPLE, enabled=True)
        self.assertEqual(result, e)

    def test_fleet_persists_multiple_devices(self):
        svc = FleetService(self.db, scenario=SITE_EXAMPLE)
        events = list(simulated_events(devices=3, frames=4))
        for e in events:
            self.assertTrue(svc.ingest(e, use_scenario=True)['accepted'])
        summary = svc.fleet_summary()
        self.assertEqual(summary['device_count'], 3)
        self.assertEqual(summary['stored_events'], 12)
        self.assertFalse(summary['safety_alerts_enabled'])
        self.assertTrue(all(row['simulated'] for row in summary['devices']))
        self.assertEqual(len(svc.repository.latest('HG-0101')), 4)

    def test_duplicate_does_not_increment_exposure(self):
        svc = FleetService(self.db, scenario=SITE_EXAMPLE)
        e = self.first
        one = svc.ingest(e)
        two = svc.ingest(e)
        self.assertTrue(one['accepted'])
        self.assertTrue(two['duplicate'])
        self.assertEqual(svc.repository.count(), 1)

    def test_exposure_gaps_not_counted(self):
        state = ExposureState()
        start = datetime(2026, 11, 11, 20, 0, tzinfo=timezone.utc)
        state.update(start.isoformat(), 35.0)
        x = state.update((start + timedelta(minutes=2)).isoformat(), 35.0)
        self.assertEqual(x['minutes_above_threshold'], 2)
        x = state.update((start + timedelta(minutes=12)).isoformat(), 35.0)
        self.assertEqual(x['minutes_above_threshold'], 2)
        self.assertEqual(x['missing_minutes'], 10)

    def test_neighbor_min_two_same_zone(self):
        events = list(simulated_events(devices=7, frames=1))
        target = copy.deepcopy(events[0])  # exterior_sol
        target['observations'] = [o for o in target['observations'] if o['parameter'] != 'relative_humidity_pct']
        latest = {e['device_id']: e for e in events if e['device_id'] != target['device_id']}
        extras = neighbor_candidates(target, latest)
        self.assertEqual(len(extras), 1)
        self.assertEqual(extras[0]['kind'], 'neighbor')
        self.assertEqual(extras[0]['parameter'], 'relative_humidity_pct')
        self.assertEqual(extras[0]['metadata']['peer_count'], 2)
        target['context']['zone_id'] = 'nonexistent'
        self.assertEqual(neighbor_candidates(target, latest), [])

    def test_phone_consent_and_wearable(self):
        x = append_gateway_sources(self.first,
          phone={'location_consent':True, 'latitude_deg':-33.4, 'longitude_deg':-70.6, 'speed_m_s':1.4},
          wearable={'physiology_consent':True,'heart_rate_bpm':105})
        keys = {o['parameter'] for o in x['observations']}
        self.assertTrue({'gps_latitude_deg','gps_longitude_deg','gps_speed_m_s','heart_rate_bpm'}.issubset(keys))
        read_event(x)
        none = append_gateway_sources(self.first,
           phone={'location_consent':False,'latitude_deg':-33.4},
           wearable={'physiology_consent':False,'heart_rate_bpm':105})
        self.assertFalse(any(o['parameter'].startswith('gps_') or o['parameter']=='heart_rate_bpm'
                             for o in none['observations']))

    def test_direct_sensitive_ingestion_requires_consent(self):
        e = copy.deepcopy(self.first)
        e['observations'].append({'parameter':'heart_rate_bpm','value':90,'unit':'bpm',
                                  'kind':'external','source':'TEST'})
        with self.assertRaisesRegex(ValueError, 'physiology_consent'):
            FleetService(self.db).ingest(e)

    def test_research_score_never_enables_safety_alerts(self):
        svc = FleetService(self.db)
        result = svc.ingest(self.first)['result']
        risk = result['occupational_research']
        self.assertFalse(risk['automatic_safety_alerts'])
        self.assertFalse(risk['score_validated'])
        self.assertEqual(result['wbgt_hybrid_research']['status'], 'model_not_loaded_or_no_physical_baseline')

    def test_restore_after_restart(self):
        e = list(simulated_events(devices=1,frames=4))
        svc = FleetService(self.db)
        for row in e:
            svc.ingest(row)
        other = FleetService(self.db)
        self.assertEqual(other.fleet_summary()['stored_events'], 4)
        self.assertAlmostEqual(other._exposure['HG-0101'].covered_minutes, 0.1, places=3)

    def test_ml_requires_real_reference_attestation(self):
        from heatguard.ml import train_csv, FEATURES
        p = Path(self.tmp.name) / 'missing.csv'
        keys = ['session_id','reference_instrument_id','reference_measured',*FEATURES,'wbgt_reference_c']
        with p.open('w', newline='', encoding='utf-8') as f:
            w=csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for i in range(40):
                r={k:30 for k in FEATURES}
                r.update(session_id=f's{i//10}',reference_instrument_id='TEST',
                         reference_measured='false',wbgt_reference_c=30)
                w.writerow(r)
        with self.assertRaisesRegex(ValueError, 'reference_measured'):
            train_csv(str(p), str(Path(self.tmp.name)/'model.joblib'))


if __name__ == '__main__':
    unittest.main()
