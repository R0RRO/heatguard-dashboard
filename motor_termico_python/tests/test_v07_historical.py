import csv
import json
import tempfile
import unittest
from pathlib import Path

from heatguard.weather_history_v07 import (
    history_url, normalize_openmeteo, load_weather_csv, save_weather_csv,
)
from heatguard.research_history_v07 import (
    wind_log_profile, analyze_history, write_report,
)
from heatguard.reference_v07 import read_measured_reference, compare_to_instrument


def fake_meteo():
    return {
        "timezone": "GMT", "utc_offset_seconds": 0, "latitude": -33.5, "longitude": -70.7,
        "hourly_units": {"temperature_2m": "°C", "relative_humidity_2m": "%",
                         "shortwave_radiation": "W/m²", "wind_speed_10m": "m/s",
                         "surface_pressure": "hPa"},
        "hourly": {
            "time": ["2025-01-10T15:00", "2025-01-10T16:00", "2025-01-10T17:00"],
            "temperature_2m": [30.0, 31.0, 32.0],
            "relative_humidity_2m": [55, 54, 52],
            "shortwave_radiation": [650.0, 800.0, 740.0],
            "wind_speed_10m": [2.0, 3.0, 1.5],
            "surface_pressure": [1008, 1007, 1008],
        }
    }


class HistoricalTests(unittest.TestCase):
    def test_url(self):
        url = history_url(-33.4, -70.6, "2025-01-10", "2025-01-11")
        self.assertIn("timezone=UTC", url)
        self.assertIn("wind_speed_unit=ms", url)
        self.assertIn("shortwave_radiation", url)
        self.assertIn("archive-api.open-meteo.com", url)

    def test_bad_range(self):
        with self.assertRaises(ValueError):
            history_url(-33.4, -70.6, "2025-01-20", "2025-01-11")
        with self.assertRaises(ValueError):
            history_url(-33.4, -70.6, "2024-01-01", "2025-06-01")

    def test_normalized_provenance_and_time(self):
        rows = normalize_openmeteo(fake_meteo())
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["timestamp_utc"], "2025-01-10T15:00:00Z")
        self.assertEqual(rows[0]["data_origin"], "reanalysis_model")
        self.assertEqual(rows[0]["solar_averaging_minutes"], 60)
        self.assertEqual(rows[0]["wind_height_m"], 10)

    def test_null_skips_not_filled(self):
        data = fake_meteo()
        data["hourly"]["wind_speed_10m"][1] = None
        rows = normalize_openmeteo(data)
        self.assertEqual(len(rows), 2)

    def test_wrong_unit_rejected(self):
        data = fake_meteo()
        data["hourly_units"]["wind_speed_10m"] = "km/h"
        with self.assertRaises(ValueError): normalize_openmeteo(data)

    def test_wrong_time_rejected(self):
        data = fake_meteo()
        data["utc_offset_seconds"] = 3600
        with self.assertRaises(ValueError): normalize_openmeteo(data)

    def test_csv_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "hist.csv"
            rows = normalize_openmeteo(fake_meteo())
            save_weather_csv(path, rows)
            read = load_weather_csv(path)
            self.assertEqual(len(read), 3)
            self.assertEqual(float(read[0]["solar_w_m2"]), 650.0)
            self.assertEqual(read[0]["data_origin"], "reanalysis_model")

    def test_reject_bad_csv_origin(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "hist.csv"
            rows = normalize_openmeteo(fake_meteo())
            rows[0]["data_origin"] = "wbgt_measured"
            with self.assertRaises(ValueError): save_weather_csv(path, rows)

    def test_wind_height_assumption(self):
        self.assertGreater(wind_log_profile(3.0, z0_m=.03), 0)
        self.assertLess(wind_log_profile(3.0, z0_m=.03), 3.0)
        with self.assertRaises(ValueError): wind_log_profile(3.0, z0_m=2.0)
        with self.assertRaises(ValueError): wind_log_profile(-1.0, z0_m=.03)

    def test_model_deltas_no_reference(self):
        rows = normalize_openmeteo(fake_meteo())
        report = analyze_history(rows)
        self.assertFalse(report["reference_measured"])
        self.assertEqual(report["n_accepted"], 3)
        self.assertEqual(len(report["scenarios"]), 7)
        self.assertEqual(report["scenarios"][0]["mean_abs_difference_c"], 0)
        self.assertNotEqual(report["scenarios"][1]["mean_abs_difference_c"], 0)
        self.assertEqual(report["predictions"][0]["latitude_deg"], -33.5)

    def test_saved_report(self):
        with tempfile.TemporaryDirectory() as d:
            report = analyze_history(normalize_openmeteo(fake_meteo()))
            files = write_report(report, d, plot=False)
            self.assertEqual(len(files), 5)
            self.assertIn("NO son métricas de precisión", Path(files[-1]).read_text(encoding="utf-8"))
            self.assertTrue(all(f.exists() for f in files))

    def test_missing_lwbgt_no_silent_fallback(self):
        import importlib.util
        if importlib.util.find_spec("lwbgt") is None:
            with self.assertRaisesRegex(RuntimeError, "lwbgt"):
                analyze_history(normalize_openmeteo(fake_meteo()), model="liljegren")

    def test_reference_is_measured_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "refs.csv"
            with p.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["timestamp_utc", "site_id", "instrument_id", "reference_origin", "wbgt_reference_c", "latitude_deg", "longitude_deg", "measurement_protocol"])
                w.writeheader()
                w.writerow({"timestamp_utc": "2025-01-10T15:00Z", "site_id": "test", "instrument_id": "WBGT-1", "reference_origin": "estimated", "wbgt_reference_c": 29.0, "latitude_deg": -33.5, "longitude_deg": -70.7, "measurement_protocol": "test"})
            with self.assertRaises(ValueError): read_measured_reference(p)

    def test_reference_rejects_synthetic_weather(self):
        report = analyze_history(normalize_openmeteo(fake_meteo()))
        refs = [{"timestamp_utc": "2025-01-10T15:00:00Z", "site_id": "S", "instrument_id": "WBGT-X", "reference_origin": "measured_instrument", "wbgt_reference_c": 26.0, "latitude_deg": -33.5, "longitude_deg": -70.7}]
        report["predictions"][0]["data_origin"] = "synthetic_fixture"
        with self.assertRaisesRegex(ValueError, "sintético"):
            compare_to_instrument(report, refs, model_site_id="S")

    def test_reference_exploratory_comparison(self):
        report = analyze_history(normalize_openmeteo(fake_meteo()))
        # Los valores del test son inventados: solo prueban la aritmética del software.
        refs = [{"timestamp_utc": "2025-01-10T15:00:00Z", "site_id": "TEST", "instrument_id": "TEST-1", "reference_origin": "measured_instrument", "wbgt_reference_c": 27.0, "latitude_deg": -33.5, "longitude_deg": -70.7}]
        result = compare_to_instrument(report, refs, model_site_id="TEST")
        self.assertEqual(result["matched"], 1)
        self.assertFalse(result["reference_authenticity_verified_by_code"])
        self.assertFalse(result["safety_certification"])
        with self.assertRaisesRegex(ValueError, "Sin pares"):
            compare_to_instrument(report, refs, model_site_id="OTRO")


if __name__ == "__main__":
    unittest.main()

class JapanReferenceTests(unittest.TestCase):
    def test_midnight_hour24(self):
        from heatguard.japan_reference_v07 import japanese_date_time
        self.assertEqual(japanese_date_time('2019/07/01','24:00'), '2019-07-01T15:00:00Z')
        self.assertEqual(japanese_date_time('2019/07/02','01:00'), '2019-07-01T16:00:00Z')

    def test_import_requires_measured_declaration(self):
        from heatguard.japan_reference_v07 import transform_observed_station_csv
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'JapanStation.csv'
            src.write_text('Date,Time,WBGT,Tg\n2019/07/01,1:00,28.2,36.0\n2019/07/01,24:00,27.1,29.0\n',encoding='utf-8')
            opts=dict(site_id='TOKYO',instrument_id='JP-MOE-REF', latitude_deg=35.68,longitude_deg=139.7)
            with self.assertRaisesRegex(ValueError,'explícitamente'):
                transform_observed_station_csv(src,**opts)
            result=transform_observed_station_csv(src,declared_measured_station=True,**opts)
            self.assertEqual(len(result),2)
            self.assertEqual(result[1]['timestamp_utc'],'2019-07-01T15:00:00Z')
