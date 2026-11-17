"""Pruebas con datos INVENTADOS: nunca representan exactitud física."""
from __future__ import annotations

import math
from datetime import datetime,timedelta,timezone

import pytest
from heatguard.benchmark_v10 import (
    scenario_weather, errors_metrics, metrics_groups, bootstrap_day_mae_ci,
    temporal_evaluation, benchmark_data,
)


def synthetic_inputs(days: int = 8):
    utc = timezone.utc
    start = datetime(2025,8,1,0,0,tzinfo=utc)
    jrows = []
    hours = {'time': [], 'temperature_2m':[], 'relative_humidity_2m':[],
             'shortwave_radiation':[], 'wind_speed_10m':[], 'surface_pressure':[]}
    for h in range(days*24):
        ts = start + timedelta(hours=h)
        solar = 650.0 if 0<= (ts.hour +9)%24 <= 10 else 0.0
        jrows.append({'wbgt_no':44132,'wbgt_date':(ts+timedelta(hours=9)).strftime('%Y/%m/%d %H:%M:%S'),
                      'wbgt_class':1,'wbgt_WI':4,'wbgt_WO':25.0+solar/260.0,
                      'wbgt_Tw':24.2,'wbgt_Tg':26.1+solar/100.0})
        hours['time'].append(ts.strftime('%Y-%m-%dT%H:%M'))
        hours['temperature_2m'].append(30.0)
        hours['relative_humidity_2m'].append(60.0)
        hours['shortwave_radiation'].append(solar)
        hours['wind_speed_10m'].append(1.8)
        hours['surface_pressure'].append(1008.0)
    jap={'status':'success', 'data':jrows}
    met={'timezone':'GMT','utc_offset_seconds':0,'latitude':35.69,'longitude':139.75,
         'hourly':hours,'hourly_units':{'temperature_2m':'°C','relative_humidity_2m':'%',
         'shortwave_radiation':'W/m²','wind_speed_10m':'m/s','surface_pressure':'hPa'}}
    return jap,met


def test_scenarios_no_mutation():
    base=[{'solar_w_m2':800.,'wind_speed_10m_m_s':3.,'timestamp_utc':'x'}]
    assert scenario_weather(base,'solar_half')[0]['solar_w_m2'] == 400
    assert scenario_weather(base,'wind_fixed_1ms')[0]['wind_speed_10m_m_s'] == 1
    assert base[0]['solar_w_m2']==800
    with pytest.raises(ValueError):scenario_weather(base,'unknown')


def test_metrics_underestimation():
    ps=[{'error_c':-3.,'jst_day':'2025-01-01'}, {'error_c':2.,'jst_day':'2025-01-02'}]
    m=errors_metrics(ps)
    assert m['mae_c']==2.5
    assert m['underestimation_gt_2c_fraction']==.5
    assert errors_metrics([]) is None


def test_day_bootstrap_reproducible():
    pairs=[{'jst_day':f'2025-01-{i:02}', 'error_c':(-1)**i *i} for i in range(1,8)]
    assert bootstrap_day_mae_ci(pairs)==bootstrap_day_mae_ci(pairs)
    assert bootstrap_day_mae_ci(pairs[:2]) is None


def test_separate_temporal_holdout():
    rows=[]
    for d in range(1,11):
        rows.extend({'jst_day':f'2025-08-{d:02}', 'error_c':d/10., 'reference_c':29.,
                     'solar_w_m2':400.,'regional_original_solar_w_m2':400.} for i in range(24))
    ev=temporal_evaluation(rows)
    assert ev['status']=='evaluated'
    assert set(ev['train_days']).isdisjoint(ev['test_days'])
    assert ev['n_train']+ev['n_test']==len(rows)
    assert temporal_evaluation(rows[:24])['status']=='blocked_insufficient_days'


def test_end_to_end_synthetic_data_not_claimed_real():
    jap,met=synthetic_inputs(days=9)
    report,pairs=benchmark_data(jap,met,station=44132,site_id='TEST_NOT_OBS',
                                 latitude=35.69,longitude=139.75)
    assert len(pairs)==9*24
    assert report['status']=='metrics_from_unverified_offline_files'
    assert not report['clip_hardware_validated']
    assert report['scenarios']['regional_full']['temporal_holdout']['status']=='evaluated'
    assert report['scenarios']['solar_zero']['metrics']['sun_ghi_gt_20']['n']>0
    assert report['scenarios']['solar_zero']['metrics']['night_ghi_le_20']['n']>0
    assert report['scenarios']['solar_half']['metrics']['all']['n']==9*24


def test_block_small_sample():
    jap,met=synthetic_inputs(days=2)
    report,_=benchmark_data(jap,met,station=44132,site_id='TEST',
                            latitude=35.69,longitude=139.75)
    assert report['status']=='blocked_no_publishable_metrics'
    assert report['scenarios']['regional_full']['status']=='blocked_insufficient_observations'


def test_filter_excludes_not_measured():
    jap,met=synthetic_inputs(days=9)
    for item in jap['data'][:6]:item['wbgt_class']=0
    for item in jap['data'][6:12]:item['wbgt_WI']=3
    rep,pairs=benchmark_data(jap,met,station=44132,site_id='TEST',
                             latitude=35.69,longitude=139.75)
    assert len(pairs)==9*24-12
    assert rep['japan_quality_counts']['not_measured_station']==6
    assert rep['japan_quality_counts']['quality_not_4']==6
