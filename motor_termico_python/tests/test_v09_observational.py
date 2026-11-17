"""Fixtures fabricados deliberadamente, solo para comprobar la mecánica del software."""
import math
import pytest
from datetime import datetime, timedelta, timezone
from heatguard.japan_api_v09 import build_url, normalize_observed, local_to_utc
from heatguard.ono_v09 import wbgt_ono
from heatguard.independent_validation_v09 import pair_and_predict, stratified_metrics, temporal_holdout_jst

def test_japan_url_typed_and_limited():
    u=build_url(44132,'2025-08-01','2025-08-03')
    assert 'data_type=1' in u and 'wbgt_nos=44132' in u
    with pytest.raises(ValueError):build_url(44132,'2025-01-01','2025-03-01')

def test_time_jst_and_nextday():
    assert local_to_utc('2025/08/01 09:00:00')=='2025-08-01T00:00:00Z'
    assert local_to_utc('2025/08/01 24:00:00')=='2025-08-01T15:00:00Z'

def make_api():
    return {'status':'success','data':[
        {'wbgt_no':44132, 'wbgt_date':'2025/08/01 09:00:00','wbgt_class':1,'wbgt_WI':'4.0','wbgt_WO':'30.1','wbgt_Tg':'37.0','wbgt_Tw':'28.0'},
        {'wbgt_no':44132, 'wbgt_date':'2025/08/01 10:00:00','wbgt_class':1,'wbgt_WI':'3.0','wbgt_WO':'30.5','wbgt_Tg':'37.0','wbgt_Tw':'28.0'},
        {'wbgt_no':44132, 'wbgt_date':'2025/08/01 11:00:00','wbgt_class':0,'wbgt_WI':'4.0','wbgt_WO':'30.5','wbgt_Tg':'37.0','wbgt_Tw':'28.0'},
    ]}

def test_reject_partial_and_forecast():
    rows,c=normalize_observed(make_api(),station_no=44132,site_id='tokyo',latitude_deg=35.69,longitude_deg=139.76)
    assert len(rows)==1 and c['quality_not_4']==1 and c['not_measured_station']==1
    assert rows[0]['timestamp_utc']=='2025-08-01T00:00:00Z'
    assert 'Tw' in rows[0]['measurement_protocol']

def test_ono_units_important():
    t,rh,rad,v=32,60,600,2
    solar=rad/1000
    target = .735*t+.0374*rh+.00292*t*rh+7.619*solar-4.557*solar**2-.0572*v-4.064
    assert math.isclose(wbgt_ono(t,rh,rad,v),target)
    with pytest.raises(ValueError):wbgt_ono(t,rh,-5,v)

def test_no_synthetic_weather_can_be_claimed_observed():
    refs,_=normalize_observed(make_api(),station_no=44132,site_id='tokyo',latitude_deg=35.69,longitude_deg=139.76)
    weather=[{'timestamp_utc':'2025-08-01T00:00:00Z','latitude_deg':35.69,'longitude_deg':139.76,
              'data_origin':'synthetic_fixture','air_temperature_c':32,'relative_humidity_pct':60,
              'solar_w_m2':650,'wind_speed_10m_m_s':2}]
    pairs,reasons=pair_and_predict(refs,weather)
    assert pairs==[] and reasons['other_origin']==1

def test_valid_contract_math_only_fixture():
    refs,_=normalize_observed(make_api(),station_no=44132,site_id='tokyo',latitude_deg=35.69,longitude_deg=139.76)
    weather=[{'timestamp_utc':'2025-08-01T00:00:00Z','latitude_deg':35.69,'longitude_deg':139.76,
              'data_origin':'reanalysis_model','air_temperature_c':32,'relative_humidity_pct':60,
              'solar_w_m2':650,'wind_speed_10m_m_s':2}]
    pairs,reasons=pair_and_predict(refs,weather)
    assert len(pairs)==1 and pairs[0]['jst_day']=='2025-08-01'
    assert stratified_metrics(pairs)['all']['n']==1
    assert temporal_holdout_jst(pairs)['status']=='insufficient_days'

def test_end_to_end_eight_synthetic_days_only_for_logic():
    """Prueba funcional integral con entradas INVENTADAS; NO debe publicarse MAE como real."""
    from heatguard.independent_validation_v09 import run_reference_study
    jp = {'status':'success','data':[]}
    hours=[]
    for i in range(8):
        day=datetime(2025,8,1)+timedelta(days=i)
        for h in range(10,16):
            local=day.replace(hour=h)
            jp['data'].append({'wbgt_no':44132,'wbgt_date':local.strftime('%Y/%m/%d %H:%M:%S'),
                 'wbgt_class':1,'wbgt_WI':'4.0','wbgt_WO':'29.1','wbgt_Tw':'27.0','wbgt_Tg':'34.0'})
            ut=local.replace(tzinfo=timezone(timedelta(hours=9))).astimezone(timezone.utc)
            hours.append(ut.strftime('%Y-%m-%dT%H:%M'))
    n=len(hours)
    weather = {'timezone':'GMT','utc_offset_seconds':0, 'latitude':35.692,'longitude':139.75,
         'hourly':{'time':hours, 'temperature_2m':[32.0]*n,'relative_humidity_2m':[60.0]*n,
                   'shortwave_radiation':[600.0]*n,'wind_speed_10m':[2.0]*n,'surface_pressure':[1008.0]*n},
         'hourly_units':{'temperature_2m':'°C','relative_humidity_2m':'%',
                         'shortwave_radiation':'W/m²','wind_speed_10m':'m/s','surface_pressure':'hPa'}}
    report, paired, refs, met = run_reference_study(jp, weather, station=44132,site_id='fixture',
             latitude=35.692,longitude=139.75,model='ono',provenance_verified=False)
    assert len(paired)==48 and report['n_pairs']==48
    assert report['temporal_holdout']['status']=='evaluated'
    assert report['offline_import_provenance_unverified'] is True
    assert len(report['temporal_holdout']['train_days_jst'])==5
    assert len(report['temporal_holdout']['test_days_jst'])==3
