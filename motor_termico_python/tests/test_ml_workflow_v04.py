import csv
import hashlib
import math
import tempfile
import unittest
from pathlib import Path
from heatguard.ml import train_csv, ResidualModel, FEATURES


class TestMlWorkflow(unittest.TestCase):
    def test_training_and_inference_on_synthetic_test_fixture_only(self):
        # SOLO TEST AUTOMATIZADO: etiquetas sintéticas que simulan pares de referencia.
        # No crea dataset real ni un modelo para usar en seguridad laboral.
        with tempfile.TemporaryDirectory() as td:
            csvfile = Path(td) / 'synthetic_reference_TEST_ONLY.csv'
            columns = ['session_id','reference_instrument_id','reference_measured',*FEATURES,'wbgt_reference_c']
            with csvfile.open('w',newline='',encoding='utf-8') as f:
                w = csv.DictWriter(f,fieldnames=columns)
                w.writeheader()
                for i in range(80):
                    base = 26 + (i % 10) * 0.3
                    row = {'session_id':f'fixture_{i//10}',
                           'reference_instrument_id':'SYNTHETIC_TEST_INSTRUMENT',
                           'reference_measured':'true',
                           'air_temperature_c':30+(i % 8)*0.2,
                           'relative_humidity_pct':40+(i % 9),
                           'solar_w_m2':500+(i % 11)*5,
                           'wind_speed_m_s':1.0+(i % 7)*0.1,
                           'pressure_hpa':1010,
                           'wbgt_physical_c':base,
                           'wbgt_reference_c':base+0.4+(i%4)*0.05}
                    w.writerow(row)
            outfile = Path(td)/'synthetic_test_model.joblib'
            metadata=train_csv(str(csvfile),str(outfile))
            self.assertEqual(metadata['training_rows'],80)
            self.assertTrue(outfile.exists())
            feature_values={
                'air_temperature_c':30.8,'relative_humidity_pct':47,
                'solar_w_m2':530,'wind_speed_m_s':1.2,
                'pressure_hpa':1010,'wbgt_physical_c':27.1,
            }
            pred=ResidualModel(str(outfile)).predict(feature_values)
            self.assertEqual(pred['status'],'research_prediction')
            self.assertFalse(pred['safety_alert_enabled'])
            self.assertTrue(math.isfinite(pred['wbgt_hybrid_c']))
            digest=hashlib.sha256(outfile.read_bytes()).hexdigest()
            verified=ResidualModel(str(outfile),expected_sha256=digest).predict(feature_values)
            self.assertTrue(verified['artifact_integrity_verified'])
            with self.assertRaisesRegex(ValueError,'SHA-256'):
                ResidualModel(str(outfile),expected_sha256='0'*64)


if __name__=='__main__': unittest.main()
