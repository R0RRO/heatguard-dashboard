import struct
import unittest
from datetime import datetime, timedelta, timezone
from heatguard.ble_existing import (
    decode_notification, ExistingClipAssembler, simulate_packets,
    TEMP_UUID, HUM_UUID, BAT_UUID, PACKET_UUID,
)
from heatguard.pipeline import evaluate
from heatguard.live import LiveStore


class TestActualFirmware(unittest.TestCase):
    def test_temp_negative_signed_little_endian(self):
        self.assertEqual(decode_notification(TEMP_UUID, struct.pack('<h', -123)),
                         {'air_temperature_c': -1.23})

    def test_humidity_scale(self):
        self.assertEqual(decode_notification(HUM_UUID, struct.pack('<H', 5842)),
                         {'relative_humidity_pct': 58.42})

    def test_battery_firmware(self):
        self.assertEqual(decode_notification(BAT_UUID, bytes([86])),
                         {'battery_level_pct': 86})

    def test_motion_struct_12_bytes(self):
        p = struct.pack('<IhhhH', 720, 1350, -55, 30, 1091)
        d = decode_notification(PACKET_UUID, p)
        self.assertEqual(d['steps_since_boot'], 720)
        self.assertEqual(d['heading_relative_deg'], 135.0)
        self.assertEqual(d['pitch_deg'], -5.5)
        self.assertEqual(d['roll_deg'], 3.0)
        self.assertEqual(d['acceleration_magnitude_g'], 1.091)
        self.assertEqual(len(p), 12)

    def test_binary_length_bad(self):
        for key in (TEMP_UUID, HUM_UUID, BAT_UUID, PACKET_UUID):
            with self.assertRaises(ValueError):
                decode_notification(key, b'')

    def test_pair_readings_no_premature_emission(self):
        a = ExistingClipAssembler('HG-101', 'z1', 'outdoor')
        instant = datetime(2026, 11, 11, 21, 0, tzinfo=timezone.utc)
        self.assertIsNone(a.ingest(TEMP_UUID, struct.pack('<h', 3150), instant))
        self.assertIsNone(a.ingest(PACKET_UUID, struct.pack('<IhhhH', 22, 100, 20, -10, 990), instant))
        event = a.ingest(HUM_UUID, struct.pack('<H', 5100), instant + timedelta(milliseconds=20))
        self.assertEqual(event['device_id'], 'HG-101')
        self.assertEqual(event['context']['zone_id'], 'z1')
        d = {x['parameter']: x for x in event['observations']}
        self.assertEqual(d['air_temperature_c']['value'], 31.5)
        self.assertEqual(d['relative_humidity_pct']['value'], 51.0)
        self.assertEqual(d['steps_since_boot']['kind'], 'estimated')
        self.assertNotIn('wind_speed_m_s', d)
        self.assertNotIn('activity_rms_g', d)  # magnitud NO es RMS de actividad
        self.assertIsNone(a.ingest(HUM_UUID, struct.pack('<H', 5200), instant + timedelta(seconds=2)))
        self.assertIsNotNone(a.ingest(TEMP_UUID, struct.pack('<h', 3140), instant + timedelta(seconds=2, milliseconds=20)))

    def test_refuses_stale_pair(self):
        a = ExistingClipAssembler('HG-1', 'unknown')
        t = datetime(2026, 11, 11, 21, 0, tzinfo=timezone.utc)
        self.assertIsNone(a.ingest(TEMP_UUID, struct.pack('<h', 3200), t))
        self.assertIsNone(a.ingest(HUM_UUID, struct.pack('<H', 5200), t + timedelta(seconds=9)))

    def test_real_simulated_bytes_pipeline(self):
        a = ExistingClipAssembler('HG-001', 'z3', 'indoor')
        events = [a.ingest(uuid, payload) for uuid, payload in simulate_packets(5)]
        event = next(x for x in events if x)
        result = evaluate(event)
        self.assertIn('heat_index_c', result['metrics'])
        self.assertEqual(result['wbgt_outdoor_model']['status'], 'missing_inputs')
        self.assertFalse(result['occupational_risk']['safety_alert_enabled'])

    def test_live_store_marks_non_normative(self):
        a = ExistingClipAssembler('HG-001', 'z3', 'unknown')
        event = next(x for uuid, payload in simulate_packets(0) if (x := a.ingest(uuid, payload)))
        result = evaluate(event)
        store = LiveStore()
        row = store.put(event, result)
        self.assertTrue(row['online'])
        self.assertFalse(row['limitations']['normative_wbgt_measurement'])
        self.assertEqual(store.get('HG-001')['data_type'], 'real_device_telemetry')

    def test_simulated_labels_do_not_impersonate_real_measurements(self):
        from heatguard.ble_existing import run_simulation
        import argparse, asyncio, contextlib, io, json
        args = argparse.Namespace(device_id='HG-001', zone='unknown', environment='unknown',
                                  weather=False, db=None, api_url=None, frames=1, interval=0,
                                  latitude=None, longitude=None, utc_offset=None,
                                  urban=None, temperature_gradient=None)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            asyncio.run(run_simulation(args))
        event = json.loads(buf.getvalue())['event']
        self.assertTrue(event['transport_metadata']['simulated'])
        self.assertTrue(all(o['kind'] == 'assumed' for o in event['observations']))
        self.assertEqual(LiveStore().put(event, evaluate(event))['data_type'], 'simulated_firmware_fixture')

    def test_out_of_bounds_battery_rejected(self):
        a = ExistingClipAssembler('HG-001', 'z3')
        with self.assertRaises(ValueError):
            a.ingest(BAT_UUID, bytes([255]))


if __name__ == '__main__':
    unittest.main()
