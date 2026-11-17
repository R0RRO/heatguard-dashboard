import csv
import json
import math
from copy import deepcopy
from pathlib import Path
import pytest

from heatguard.thermal_science import experimental_balance_c
from heatguard.sensitivity import DEFAULT_CASE, analyze, load_case, save_report
from heatguard.scientific_validation import evaluate_csv
from heatguard.pipeline import evaluate


def sample_case():
    return deepcopy(DEFAULT_CASE)


def event():
    return {
        'device_id': 'HG-TEST', 'timestamp': '2026-11-11T17:00:00-03:00',
        'context': {'zone_id': 'exterior', 'environment': 'outdoor',
                    'science': {'enable_simplified_balance': True, 'wind_is_local': True}},
        'observations': [
            {'parameter': k, 'value': v, 'unit': unit, 'kind': 'measured', 'source': 'FAKE_TEST'}
            for k, v, unit in (
                ('air_temperature_c', 32, 'degC'), ('relative_humidity_pct', 60, 'percent'),
                ('solar_w_m2', 650, 'W/m2'), ('wind_speed_m_s', 1.5, 'm/s'),
                ('pressure_hpa', 1008, 'hPa'))]
    }


def test_balance_finite_and_component_ranges():
    r = experimental_balance_c(32, 60, 650, 1.5, 1008)
    assert r['model'] == 'heatguard_simplified_energy_balance_v1'
    assert r['normative_measurement'] is False
    assert r['virtual_globe_c'] > 32
    assert 18 < r['virtual_natural_wet_bulb_c'] < 32
    assert 27 < r['wbgt_like_experimental_c'] < 33


def test_solar_increases_experimental_output_with_fixed_conditions():
    a = experimental_balance_c(32, 60, 0, 1.5, 1008)
    b = experimental_balance_c(32, 60, 800, 1.5, 1008)
    assert b['wbgt_like_experimental_c'] > a['wbgt_like_experimental_c']


def test_high_wind_reduces_solar_heating_in_example():
    slow = experimental_balance_c(32, 60, 700, 0.3, 1008)
    fast = experimental_balance_c(32, 60, 700, 3, 1008)
    assert slow['virtual_globe_c'] > fast['virtual_globe_c']
    assert slow['wbgt_like_experimental_c'] > fast['wbgt_like_experimental_c']


@pytest.mark.parametrize('params', [
    (32, 60, 700, 0, 1008), (32, 105, 700, 1.5, 1008),
    (32, 60, -2, 1.5, 1008), (32, 60, 700, 1.5, 10),
    (float('nan'), 60, 700, 1.5, 1008)
])
def test_out_of_domain_rejected(params):
    with pytest.raises(ValueError):
        experimental_balance_c(*params)


def test_local_sensitivity_nonzero_for_solar_and_wind():
    r = analyze(sample_case(), samples=60, seed=10)
    grads = {x['parameter']: x['sensitivity_c_per_unit'] for x in r['local_derivatives']}
    assert grads['solar_w_m2'] > 0
    assert grads['wind_speed_m_s'] < 0
    assert r['normative_measurement'] is False


def test_monte_carlo_reproducible_and_informative():
    first = analyze(sample_case(), samples=120, seed=12)
    second = analyze(sample_case(), samples=120, seed=12)
    assert first == second
    rows = {r['scenario']: r for r in first['scenario_comparison']}
    assert rows['ambos_sensores']['scenario_spread_90_c'] < rows['sin_sensor_adicional']['scenario_spread_90_c']


def test_bad_range_rejected():
    case = sample_case()
    case['uncertainty_ranges']['wind_speed_m_s'] = [-3, 4]
    with pytest.raises(ValueError):
        analyze(case, samples=60)


def test_liljegren_no_silent_fallback_when_missing():
    from heatguard.sensitivity import model_function
    try:
        import lwbgt
    except ImportError:
        with pytest.raises(RuntimeError, match='lwbgt'):
            model_function(sample_case(), 'liljegren')


def test_report_files(tmp_path):
    report = analyze(sample_case(), samples=60)
    files = save_report(report, tmp_path, plots=False)
    assert len(files) == 4
    assert 'NO' in (tmp_path / 'RESUMEN_RESULTADOS.md').read_text()


def test_pipeline_off_by_default():
    payload = event()
    del payload['context']['science']
    assert evaluate(payload)['experimental_balance']['status'] == 'disabled'


def test_pipeline_requires_explicit_local_wind():
    payload = event()
    del payload['context']['science']['wind_is_local']
    assert evaluate(payload)['experimental_balance']['status'] == 'wind_reference_uncertain'


def test_pipeline_experimental_with_sources():
    payload=event()
    payload['observations'][2]['kind']='assumed'
    out=evaluate(payload)
    assert out['experimental_balance']['status'] == 'computed'
    assert out['experimental_balance']['input_sources']['solar_w_m2']['kind']=='assumed'
    assert out['experimental_balance']['risk_alerts_enabled'] is False


def test_validation_rejects_fake_reference(tmp_path):
    path = tmp_path / 'bad.csv'
    path.write_text('sample_id,session_id,reference_instrument_id,reference_origin,timestamp,wbgt_reference_c,air_temperature_c,relative_humidity_pct,solar_w_m2,wind_speed_m_s,pressure_hpa\n'
                    '1,A,INST-01,simulated,2026-11-11T17:00:00-03:00,29.2,32,60,650,1.5,1008\n')
    with pytest.raises(ValueError, match='measured_instrument'):
        evaluate_csv(path)


def test_validation_metrics_with_test_fixture_only(tmp_path):
    # Synthetic test fixture only: NOT supplied as user data or model training.
    path = tmp_path / 'test_fixture_only.csv'
    fields = ['sample_id','session_id','reference_instrument_id','reference_origin','timestamp',
              'wbgt_reference_c','air_temperature_c','relative_humidity_pct','solar_w_m2','wind_speed_m_s','pressure_hpa']
    with path.open('w', newline='') as f:
        w=csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for i in range(3):
            w.writerow(dict(sample_id=str(i), session_id='TEST_DAY', reference_instrument_id='TEST_ONLY',
                            reference_origin='measured_instrument', timestamp='2026-11-11T17:00:00-03:00',
                            wbgt_reference_c=29.3+i*.2, air_temperature_c=32, relative_humidity_pct=60,
                            solar_w_m2=650, wind_speed_m_s=1.5, pressure_hpa=1008))
    result=evaluate_csv(path)
    assert result['summary']['n']==3
    assert result['metadata_unverified'] is True
    assert result['measurement_conformity_iso'] is False


def test_api_science_endpoint():
    try:
        from fastapi.testclient import TestClient
        from heatguard.api import app
    except ImportError:
        pytest.skip('FastAPI optional not installed')
    client=TestClient(app)
    response=client.post('/v1/research/sensitivity', json={'samples': 60, 'seed': 2})
    assert response.status_code == 200
    assert response.json()['normative_measurement'] is False
