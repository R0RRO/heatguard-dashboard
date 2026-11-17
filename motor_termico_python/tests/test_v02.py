import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs

from heatguard.ble_bridge import LineFrames, packet_to_event
from heatguard.pipeline import evaluate
from heatguard.storage import latest_records, save_record
from heatguard.weather import WeatherProvider, build_url, parse_openmeteo

ROOT = Path(__file__).resolve().parents[1]


def fixture(name):
    return json.loads((ROOT / 'examples' / name).read_text(encoding='utf8'))


class TestFrames(unittest.TestCase):
    def test_fragmented_and_combined(self):
        assembler = LineFrames()
        self.assertEqual(assembler.feed(b'{"temperature_c":31.2'), [])
        self.assertEqual(assembler.feed(b',"humidity_pct":60}\n{"temperature_c":31'),
                         ['{"temperature_c":31.2,"humidity_pct":60}'])
        self.assertEqual(assembler.feed(b',"humidity_pct":59}\n'),
                         ['{"temperature_c":31,"humidity_pct":59}'])

    def test_oversize(self):
        assembler = LineFrames(max_bytes=12)
        with self.assertRaises(ValueError):
            assembler.feed(b'123456789012345')
        self.assertEqual(assembler.buffer, b'')

    def test_packet_is_compatible_with_v01(self):
        dt = datetime(2026, 11, 11, 17, 0, tzinfo=timezone.utc)
        event = packet_to_event(
            '{"temperature_c":31.2,"humidity_pct":57,"activity_rms_g":0.2,"seq":10}',
            'HG-9', 'Z-A', {'environment': 'outdoor'}, received_at=dt)
        output = evaluate(event)
        self.assertIn('heat_index_c', output['metrics'])
        self.assertEqual(output['inputs_selected']['air_temperature_c']['kind'], 'measured')
        self.assertEqual(output['inputs_selected']['activity_rms_g']['value'], 0.2)
        self.assertEqual(event['transport_metadata']['extra']['seq'], 10)
        self.assertFalse(output['occupational_risk']['safety_alert_enabled'])

    def test_invalid_packet_no_humidity(self):
        with self.assertRaises(ValueError):
            packet_to_event('{"temperature_c":31.2}', 'HG', 'Z')

    def test_invalid_humidity(self):
        with self.assertRaises(ValueError):
            packet_to_event('{"temperature_c":31.2,"humidity_pct":150}', 'HG', 'Z')


class TestWeather(unittest.TestCase):
    def test_url_units_utc(self):
        url = build_url(-33.45, -70.66)
        q = parse_qs(urlparse(url).query)
        self.assertEqual(q['wind_speed_unit'], ['ms'])
        self.assertEqual(q['timezone'], ['GMT'])
        self.assertIn('surface_pressure', q['hourly'][0])

    def test_weather_labels_and_source(self):
        readings = parse_openmeteo(fixture('weather_fixture.json'), '2026-11-11T17:20:00Z')
        obs = {x['parameter']: x for x in readings}
        self.assertEqual(obs['wind_speed_m_s']['value'], 2.5)
        self.assertEqual(obs['wind_speed_m_s']['source'], 'OPEN_METEO_HOURLY_MODEL')
        self.assertEqual(obs['wind_speed_m_s']['metadata']['height_m'], 10)
        self.assertEqual(obs['solar_w_m2']['metadata']['temporal_mean'], 'preceding_1h')
        self.assertEqual(obs['pressure_hpa']['value'], 970.3)

    def test_old_weather_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Sin registro horario'):
            parse_openmeteo(fixture('weather_fixture.json'), '2026-11-14T12:00:00Z')

    def test_measured_wins_regional(self):
        payload = fixture('outdoor_scenario.json')
        provider = WeatherProvider(fetch=lambda _: fixture('weather_fixture.json'))
        enriched, warnings = provider.enrich(payload)
        output = evaluate(enriched)
        self.assertEqual(output['inputs_selected']['air_temperature_c']['source'], 'HTU21D')
        # La hipótesis queda reemplazada por el modelo externo.
        self.assertEqual(output['inputs_selected']['wind_speed_m_s']['value'], 2.5)
        self.assertEqual(output['inputs_selected']['wind_speed_m_s']['kind'], 'external')
        self.assertEqual(output['inputs_selected']['solar_w_m2']['value'], 640)
        self.assertTrue(warnings)
        self.assertEqual(enriched['context']['weather_model']['averaging_minutes'], 60)
        self.assertEqual(enriched['context']['weather_model']['wind_height_m'], 10)
        self.assertEqual(len(provider.cache), 1)
        provider.enrich(payload)
        self.assertEqual(len(provider.cache), 1)

    def test_no_network_for_indoor(self):
        payload = fixture('outdoor_scenario.json')
        payload['context']['environment'] = 'indoor'
        provider = WeatherProvider(fetch=lambda _: self.fail('No hacer solicitud'))
        enriched, warnings = provider.enrich(payload)
        self.assertEqual(enriched, payload)
        self.assertIn('omitida', warnings[0])

    def test_failure_does_not_invent_values(self):
        payload = fixture('base_only.json')
        provider = WeatherProvider(fetch=lambda _: (_ for _ in ()).throw(OSError('offline')))
        enriched, warnings = provider.enrich(payload)
        self.assertEqual(enriched['observations'], payload['observations'])
        self.assertTrue(warnings)


class TestStorage(unittest.TestCase):
    def test_sqlite_round_trip(self):
        event = fixture('base_only.json')
        result = evaluate(event)
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / 'data' / 'heatguard.db')
            save_record(db, event, result)
            recs = latest_records(db)
            self.assertEqual(len(recs), 1)
            self.assertEqual(recs[0]['result']['device_id'], event['device_id'])
            self.assertEqual(recs[0]['event']['observations'][0]['parameter'], 'air_temperature_c')


if __name__ == '__main__':
    unittest.main()
