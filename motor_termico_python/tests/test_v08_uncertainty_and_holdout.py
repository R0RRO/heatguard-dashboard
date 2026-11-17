"""Todas las entradas de referencia inventadas aquí son FIXTURES de test, NO datos de validación."""
import copy
import json
from pathlib import Path
import pytest
from heatguard.weather_history_v07 import load_weather_csv
from heatguard.uncertainty_v08 import analyze_uncertainty, UNCERTAINTY_SCHEMES, save_uncertainty_report, _triangle_from_uniform
from heatguard.field_validation_v08 import chronological_validation, evaluate_model_report
from heatguard.reference_v07 import compare_to_instrument

FIXTURE = Path(__file__).resolve().parents[1] / "config" / "meteorologia_SINTETICA_24h.csv"


def test_v08_seed_reproducible_and_origin_explicit():
    rows = load_weather_csv(FIXTURE)
    a = analyze_uncertainty(rows[:2], n_samples=40, seed=4)
    b = analyze_uncertainty(rows[:2], n_samples=40, seed=4)
    assert a == b
    assert a['accuracy_vs_instrument_evaluated'] is False
    assert a['statistical_confidence_interval'] is False
    assert a['model_output_type'] == 'EXPERIMENTAL_PROXY_NOT_WBGT'
    assert len(a['bands']) == 8
    assert all('SYNTHETIC_INPUT' in x['input_label'] for x in a['bands'])


def test_v08_intervals_shrink_only_under_assumptions():
    out = analyze_uncertainty(load_weather_csv(FIXTURE), n_samples=60, seed=22)
    d = {x['scenario']: x['mean_model_band_width_c'] for x in out['summary_daylight']}
    assert d['ideal_both_measurements'] < d['regional_only']
    assert d['ideal_solar_measurement'] < d['regional_only']
    assert out['sensor_modes_are_idealized'] is True
    assert 'NO' in out['limitations'][0] or 'intervalos' in out['limitations'][0]


def test_v08_saved_reports_mark_assumptions(tmp_path):
    result = analyze_uncertainty(load_weather_csv(FIXTURE)[:3], n_samples=20)
    save_uncertainty_report(result, tmp_path)
    j = json.loads((tmp_path / 'uncertainty_report.json').read_text(encoding='utf-8'))
    assert j['statistical_confidence_interval'] is False
    assert (tmp_path / 'uncertainty_bands.csv').exists()
    assert 'NO es precisión' in (tmp_path / 'RESUMEN.md').read_text(encoding='utf-8')


def test_v08_cannot_claim_real_validation_from_synthetic_weather():
    src = load_weather_csv(FIXTURE)[0]
    pseudo_model_report = {'model': 'balance', 'predictions': [
      {'timestamp_utc': src['timestamp_utc'], 'latitude_deg': src['latitude_deg'],
       'longitude_deg': src['longitude_deg'], 'baseline_full_external': 30,
       'solar_w_m2': 300, 'data_origin': 'synthetic_fixture'}]}
    # Sólo para probar barreras de seguridad de datos: NO es observación real.
    refs = [{'site_id': 'JP_TEST', 'timestamp_utc': src['timestamp_utc'],
             'latitude_deg': src['latitude_deg'], 'longitude_deg': src['longitude_deg'],
             'reference_origin': 'measured_instrument', 'wbgt_reference_c': 30,
             'instrument_id':'TEST_ONLY'}]
    with pytest.raises(ValueError, match='sintético'):
       evaluate_model_report(pseudo_model_report, refs, site_id='JP_TEST')


def _pairs(n_days=6, per_day=6):
    return [{'timestamp_utc': f'2025-08-{d:02d}T{h:02d}:00:00Z', 'error_c': 0.4 + .1*d,
             'site_id':'TEST_ONLY','reference_c':30.0, 'model_c':30.4+.1*d,
             'solar_w_m2':400} for d in range(1,n_days+1) for h in range(10,10+per_day)]


def test_v08_chronological_validation_avoids_test_leakage():
    result = chronological_validation(_pairs())
    assert result['status'] == 'exploratory_temporal_holdout_completed'
    assert max(result['train_dates']) < min(result['test_dates'])
    assert result['n_train'] == 24 and result['n_test'] == 12
    assert result['test_uncorrected']['mae_c'] != result['test_bias_corrected']['mae_c']
    assert 0 <= result['test_empirical_coverage'] <= 1
    assert result['research_only'] is True


def test_v08_insufficient_days_refuses_holdout():
    r=chronological_validation(_pairs(n_days=2))
    assert r['status'] == 'insufficient_independent_days'


def test_v08_input_checks():
    with pytest.raises(ValueError): analyze_uncertainty([], n_samples=20)
    with pytest.raises(ValueError): analyze_uncertainty(load_weather_csv(FIXTURE)[:1], n_samples=2)
    with pytest.raises(ValueError): _triangle_from_uniform(.5, 1, .5)
    with pytest.raises(ValueError): chronological_validation(_pairs(), alpha=1)


def test_v08_solar_zero_stays_zero_in_all_scenarios():
    first = load_weather_csv(FIXTURE)[0]
    assert float(first['solar_w_m2']) == 0
    result = analyze_uncertainty([first], n_samples=30)
    assert all(r['solar_w_m2']==0 for r in result['bands'])
