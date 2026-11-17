import math
import pytest
from heatguard.case_radiation import (CaseAssumptions, surface_equilibrium_c,
    inferred_solar_for_wind, ambiguity_study, relative_brightness)
from heatguard.relative_wind import relative_wind
from heatguard.research_v06 import run_experiments, save_results


def test_surface_inversion_fixed_wind_reproduces_input():
    a = CaseAssumptions()
    ts = surface_equilibrium_c(32, 650, 1.5, a)
    assert abs(inferred_solar_for_wind(ts,32,1.5,a) - 650) < 1e-6


def test_more_solar_heats_surface():
    assert surface_equilibrium_c(32,650,1) > surface_equilibrium_c(32,0,1)


def test_more_wind_cools_illuminated_surface():
    assert surface_equilibrium_c(32,650,3) < surface_equilibrium_c(32,650,0.3)


def test_case_surface_nonidentifiability():
    ts=surface_equilibrium_c(32,650,1.5)
    r=ambiguity_study(ts,32,0.2,4)
    assert r['identified'] is False
    assert r['spread_of_conditional_solar_w_m2'] > 0


def test_lux_never_becomes_irradiance():
    r=relative_brightness(18000,95000)
    assert r['solar_irradiance_w_m2'] is None
    assert 0 < r['brightness_fraction'] < 1


def test_lux_validation():
    with pytest.raises(ValueError):relative_brightness(10,0)


def test_wind_bounds_without_direction():
    r=relative_wind(2,1.5)
    assert r['relative_speed_m_s'] is None
    assert r['possible_speed_range_m_s']==[0.5,3.5]


def test_wind_vector_same_direction():
    r=relative_wind(2,1.5,90,90)
    assert math.isclose(r['relative_speed_m_s'],0.5)


def test_wind_vector_opposite_direction():
    r=relative_wind(2,1.5,90,270)
    assert math.isclose(r['relative_speed_m_s'],3.5)


def test_wind_one_direction_is_invalid():
    with pytest.raises(ValueError):relative_wind(2,1.5,90)


def test_experiment_never_claims_reference():
    result=run_experiments()
    assert result['reference_wbgt_data_used'] is False
    assert result['sensor_candidates'][0]['component_price_clp'] is None


def test_report_export(tmp_path):
    files=save_results(run_experiments(),tmp_path)
    assert (tmp_path/'research_report_v06.json').exists()
    assert (tmp_path/'surface_radiation_ambiguity.csv').exists()
    assert all(p.exists() for p in files)


def test_model_crosscheck_rejects_mixed_height():
    from heatguard.sensitivity import load_case
    from heatguard.model_crosscheck import compare
    result=compare(load_case())
    assert result['status']=='incompatible_wind_metadata'


def test_model_crosscheck_missing_lwbgt_explicit():
    from heatguard.sensitivity import load_case
    from heatguard.model_crosscheck import compare
    case=load_case()
    case['liljegren_context']['weather_model']['wind_height_m']=2
    result=compare(case)
    assert result['reference_measured'] is False
    assert result['status'] in ('liljegren_not_computed','models_compared')
