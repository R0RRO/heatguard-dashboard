"""Controles para entrenamiento exploratorio v0.20."""
import pytest
import pandas as pd
from heatguard.historical_ml_v20 import check_table, split_data, measure, research_predict


def fixture_df():
    rows=[]
    for site in ("JP_TOKYO", "JP_FUKUOKA"):
        for day in ("2025-08-01","2025-08-14","2025-08-15","2025-08-31"):
            rows.append({"site_id":site,"timestamp_utc":day+"T00:00:00Z", "jst_day":day,
                "reference_c":28.5, "ono_c":28.0,"liljegren_c":29.0,
                "temperature_c":30,"relative_humidity_pct":65,
                "solar_w_m2":200,"wind_10m_m_s":3,"pressure_hpa":1010,
                "hour_sin":0,"hour_cos":1,"air_data_origin":"open_meteo_reanalysis"})
    return pd.DataFrame(rows)


def test_integrity_and_site_time_partition():
    df=fixture_df()
    assert check_table(df)
    tr, te = split_data(df, "JP_FUKUOKA")
    assert len(tr)==2 and len(te)==2
    assert set(tr.site_id)=={"JP_TOKYO"}
    assert set(te.site_id)=={"JP_FUKUOKA"}
    assert max(tr.jst_day)<min(te.jst_day)


def test_duplicates_blocked():
    df=fixture_df()
    with pytest.raises(ValueError,match="duplicad"):
        check_table(pd.concat([df,df.iloc[[0]]],ignore_index=True))


def test_local_sensor_domain_blocked():
    df=fixture_df();df.loc[0,"air_data_origin"]="clip_htu21d_measured"
    with pytest.raises(ValueError,match="Dominio"):
        check_table(df)
    with pytest.raises(ValueError,match="BLOQUEADO"):
        research_predict("inexistente.joblib",{},air_data_origin="clip_htu21d_measured")


def test_invalid_values_blocked():
    df=fixture_df(); df.loc[0,"ono_c"]=float('nan')
    with pytest.raises(ValueError):check_table(df)


def test_metrics_threshold_and_underestimation():
    r=measure([29,29,27,29],[27,28.9,29,26])
    assert r["n"]==4 and r["high_reference_n"]==3
    assert r["false_low_n"]==2
    assert r["false_high_n"]==1
    assert r["underestimate_gt1_when_high_n"]==2
    assert r["underestimate_gt2_when_high_n"]==1


def test_measure_incompatible_arrays_rejected():
    with pytest.raises(ValueError):measure([27],[26,26])
