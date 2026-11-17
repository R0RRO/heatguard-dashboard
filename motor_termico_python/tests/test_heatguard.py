import copy
import json
import unittest
from pathlib import Path

from heatguard import evaluate
from heatguard.schema import Observation
from heatguard.thermal import heat_index_nws_c, wet_bulb_stull_c

HERE = Path(__file__).resolve().parents[1] / "examples"


def example(name="base_only.json"):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


class TestThermal(unittest.TestCase):
    def test_nws_heat_index_90f_70rh(self):
        # Valor tabulado aproximado: 90 °F, 70% HR -> 105.9 °F.
        result_f = heat_index_nws_c((90 - 32) * 5 / 9, 70) * 9 / 5 + 32
        self.assertAlmostEqual(result_f, 105.9, delta=1.0)

    def test_stull_physical_sanity(self):
        tw = wet_bulb_stull_c(32, 60)
        self.assertIsNotNone(tw)
        self.assertGreater(tw, 15)
        self.assertLess(tw, 32)

    def test_stull_outside_domain(self):
        self.assertIsNone(wet_bulb_stull_c(32, 100))


class TestPipeline(unittest.TestCase):
    def test_base_has_not_iso_wbgt(self):
        out = evaluate(example())
        self.assertIn("heat_index_c", out["metrics"])
        self.assertIn("shade_experimental_proxy_c", out["metrics"])
        self.assertEqual(out["wbgt_outdoor_model"]["status"], "missing_inputs")
        self.assertFalse(out["occupational_risk"]["safety_alert_enabled"])
        self.assertFalse(out["limitations"]["normative_wbgt_measurement"])

    def test_sensor_replaces_assumption(self):
        out = evaluate(example("sensor_upgrade.json"))
        solar = out["inputs_selected"]["solar_w_m2"]
        wind = out["inputs_selected"]["wind_speed_m_s"]
        self.assertEqual(solar["value"], 720.0)
        self.assertEqual(solar["kind"], "external")
        self.assertEqual(wind["value"], 1.8)
        self.assertEqual(wind["source"], "ESTACION_FAENA_ANEMOMETRO_10M")
        self.assertEqual(out["inputs_selected"]["heart_rate_bpm"]["value"], 95)

    def test_invalid_humidity_rejected(self):
        obj = example()
        obj["observations"][1]["value"] = 120
        with self.assertRaises(ValueError):
            evaluate(obj)

    def test_neighbor_other_zone_rejected(self):
        obj = example()
        obj["observations"].append({
            "parameter": "solar_w_m2", "value": 500, "unit": "W/m2",
            "kind": "neighbor", "source": "HG-002", "zone_id": "OTRA_ZONA",
        })
        result = evaluate(obj)
        self.assertNotIn("solar_w_m2", result["inputs_selected"])
        self.assertEqual(len(result["inputs_rejected"]), 1)

    def test_older_external_reading_rejected(self):
        obj = example()
        obj["observations"].append({
            "parameter": "wind_speed_m_s", "value": 3,
            "unit": "m/s", "kind": "external", "source": "ESTACION",
            "timestamp": "2026-11-11T15:00:00Z"
        })
        result = evaluate(obj)
        self.assertNotIn("wind_speed_m_s", result["inputs_selected"])

    def test_nonfinite_rejected(self):
        with self.assertRaises(ValueError):
            Observation.from_dict({"parameter": "solar_w_m2", "value": float("nan"),
                                   "unit": "W/m2", "kind": "assumed", "source": "x"})


if __name__ == "__main__":
    unittest.main()

class TestLiljegrenAdapter(unittest.TestCase):
    def test_indoor_model_disabled(self):
        from heatguard.liljegren import calculate_optional
        data = example("outdoor_scenario.json")
        data["context"]["environment"] = "indoor"
        vals = {x["parameter"]: x["value"] for x in data["observations"]}
        out = calculate_optional(vals, data["timestamp"], data["context"])
        self.assertEqual(out["status"], "not_applicable")

    def test_adapter_with_mock_engine(self):
        # Prueba de integración de argumentos sin depender de la instalación opcional.
        import sys
        from unittest.mock import patch
        from types import SimpleNamespace
        from heatguard.liljegren import calculate_optional
        data = example("outdoor_scenario.json")
        vals = {x["parameter"]: x["value"] for x in data["observations"]}
        captured = {}

        def fake_input(**kwargs):
            captured.update(kwargs)
            return kwargs

        fake_module = SimpleNamespace(
            Input=fake_input,
            calculate=lambda x: SimpleNamespace(status=0, wbgt_c=28.37),
        )
        with patch.dict(sys.modules, {"lwbgt": fake_module}):
            out = calculate_optional(vals, data["timestamp"], data["context"])
        self.assertEqual(out["status"], "computed")
        self.assertEqual(out["value_c"], 28.37)
        self.assertEqual(captured["hour"], 14)  # 17:00 UTC -> 14:00 UTC-3
        self.assertEqual(captured["gmt_offset_hours"], -3)
        self.assertEqual(captured["solar_w_m2"], 650)
