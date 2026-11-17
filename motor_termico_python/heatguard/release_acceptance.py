"""Deterministic software acceptance laboratory for the v0.30 release.

Every event is visibly simulated.  Passing this laboratory verifies software
logic and persistence only; it is not physical or occupational validation.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .fleet import FleetService


T0 = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)


def _obs(parameter: str, value: float, unit: str, *, kind: str = 'assumed',
         source: str = 'VIRTUAL_ACCEPTANCE_NOT_HARDWARE') -> dict[str, Any]:
    return {'parameter':parameter,'value':value,'unit':unit,'kind':kind,
            'source':source,'quality':'unverified'}


def event(name: str, when: datetime, *, temperature: float | None = 31,
          humidity: float | None = 55, solar: float | None = 400,
          wind: float | None = 1.0, pressure: float | None = 1010,
          battery: float = 80, steps: int = 20, acceleration: float = 1.0,
          environment: str = 'outdoor', activity: str = 'moderate',
          worker: str | None = None, observations: list[dict] | None = None) -> dict:
    rows = [] if observations is None else list(observations)
    for parameter,value,unit in (
        ('air_temperature_c',temperature,'degC'),('relative_humidity_pct',humidity,'percent'),
        ('solar_w_m2',solar,'W/m2'),('wind_speed_m_s',wind,'m/s'),
        ('pressure_hpa',pressure,'hPa'),('battery_level_pct',battery,'percent'),
        ('steps_since_boot',steps,'count'),('acceleration_magnitude_g',acceleration,'g')):
        if value is not None:
            rows.append(_obs(parameter,value,unit))
    return {
        'event_id':f'{name}-{int(when.timestamp())}', 'device_id':f'HG-ACC-{name}',
        'timestamp':when.isoformat(),
        'transport_metadata':{'simulated':True,'transport':'release_acceptance_fixture'},
        'context':{
            'zone_id':name,'worker_id':worker or f'virtual-{name}',
            'environment':environment,'activity_class':activity,
            'activity_source':'acceptance_scenario','work_state':'resting' if activity=='resting' else 'working',
            'shift_duration_hours':8,
            'location':{'latitude_deg':-33.45,'longitude_deg':-70.66,'utc_offset_hours':-3},
            'weather_model':{'wind_height_m':2,'averaging_minutes':10,'urban':1,
                             'vertical_temperature_difference_c':0},
            'research_review':{'enabled':True,'threshold_c':28,
                'illustrative_half_width_c':1.5,'duration_review_min':2,
                'hysteresis_c':.5,'repeat_suppression_min':30,
                'minimum_coverage_fraction':0,'origin':'SOFTWARE_ACCEPTANCE_NOT_LIMIT'},
            'radiation':{'mode':'differential','black_surface_c':temperature+5 if temperature else 30,
                         'white_surface_c':temperature+1 if temperature else 29,
                         'source_kind':'assumed','source_id':'VIRTUAL_DIFFERENTIAL_NOT_INSTALLED'},
        },
        'observations':rows,
    }


def _ingest(fleet: FleetService, item: dict) -> dict:
    response = fleet.ingest(item)
    if not response.get('accepted'):
        raise RuntimeError(f"Evento de aceptación rechazado: {response}")
    return response['result']


def run_release_acceptance(out: str | Path, db: str | Path) -> dict[str, Any]:
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    db = Path(db)
    fleet = FleetService(str(db))
    evidence: dict[str, dict] = {}

    evidence['sun_work'] = _ingest(fleet,event('sun',T0,temperature=34,humidity=45,solar=850,wind=.7,activity='heavy'))
    evidence['shade_work'] = _ingest(fleet,event('shade',T0,temperature=31,humidity=55,solar=70,wind=1.4))
    evidence['low_ventilation'] = _ingest(fleet,event('indoor',T0,temperature=33,humidity=65,solar=None,wind=None,
                                                      pressure=None,environment='indoor'))
    evidence['stationary_heavy'] = _ingest(fleet,event('stationary',T0,temperature=33,humidity=52,solar=550,
                                                        wind=.3,steps=0,acceleration=1.15,activity='heavy'))
    rest_worker='virtual-rest-worker'
    _ingest(fleet,event('rest',T0,temperature=27,humidity=55,solar=80,wind=2,activity='resting',worker=rest_worker))
    evidence['rest'] = _ingest(fleet,event('rest',T0+timedelta(minutes=3),temperature=27,humidity=55,solar=80,
                                           wind=2,activity='resting',worker=rest_worker))
    _ingest(fleet,event('rapid',T0,temperature=28,humidity=50))
    evidence['rapid_change'] = _ingest(fleet,event('rapid',T0+timedelta(minutes=1),temperature=36,humidity=50))
    _ingest(fleet,event('gap',T0,temperature=32,humidity=55))
    evidence['connectivity_gap'] = _ingest(fleet,event('gap',T0+timedelta(minutes=15),temperature=32,humidity=55))
    evidence['sensor_disconnected'] = _ingest(fleet,event('disconnected',T0,temperature=None,humidity=None,
        solar=None,wind=None,pressure=None,battery=70))
    contradictory = [_obs('air_temperature_c',30,'degC',kind='external',source='VIRTUAL_STATION'),
                     _obs('air_temperature_c',35,'degC',kind='assumed',source='VIRTUAL_MANUAL')]
    evidence['anomalous_readings'] = _ingest(fleet,event('anomaly',T0,temperature=None,observations=contradictory))
    evidence['low_battery'] = _ingest(fleet,event('battery',T0,battery=5))

    recovery_worker='virtual-recovery-worker'
    _ingest(fleet,event('recovery',T0,worker=recovery_worker))
    _ingest(fleet,event('recovery',T0+timedelta(minutes=2),worker=recovery_worker))
    restored = FleetService(str(db))
    evidence['server_recovery'] = _ingest(restored,event('recovery',T0+timedelta(minutes=4),worker=recovery_worker))

    checks = [
        ('sun_and_shade_computed', all(evidence[x]['environmental_estimator_v18']['status']=='computed'
                                      for x in ('sun_work','shade_work'))),
        ('sun_exceeds_shade', evidence['sun_work']['environmental_estimator_v18']['value_c'] >
                              evidence['shade_work']['environmental_estimator_v18']['value_c']),
        ('indoor_safe_degradation', evidence['low_ventilation']['environmental_estimator_v18']['status']=='not_applicable'),
        ('stationary_heavy_not_inferred_from_steps', evidence['stationary_heavy']['occupational_research']['context_model']['metabolic_rate_inferred_from_steps'] is False),
        ('rest_integrated', evidence['rest']['exposure_timeline_v22']['current_recovery_duration_minutes']==3),
        ('rapid_change_flagged', 'ABRUPT_T_CHANGE' in evidence['rapid_change']['engineering_quality_v19']['flag_codes']),
        ('gap_is_unknown_not_safe', evidence['connectivity_gap']['exposure_timeline_v22']['missing_minutes']==15),
        ('disconnected_sensor_flagged', 'MISSING_SENSOR_PAIR' in evidence['sensor_disconnected']['engineering_quality_v19']['flag_codes']),
        ('contradiction_flagged', 'CONTRADICTORY_SOURCES' in evidence['anomalous_readings']['engineering_quality_v19']['flag_codes']),
        ('low_battery_flagged', 'LOW_BATTERY' in evidence['low_battery']['engineering_quality_v19']['flag_codes']),
        ('restart_preserves_exposure', evidence['server_recovery']['exposure_timeline_v22']['covered_minutes']==4),
        ('all_simulated', all(value['provenance_summary']['simulated'] for value in evidence.values())),
        ('no_actuator_commands', all(not value.get('review_state_v23',{}).get('automatic_actuator_command',False)
                                     for value in evidence.values())),
    ]
    report = {
        'status':'passed' if all(passed for _,passed in checks) else 'failed',
        'software_release':'0.30.0-rc1','simulation_only':True,'physical_hardware_used':False,
        'occupational_validation_performed':False,'scenario_count':len(evidence),
        'checks':[{'check':name,'passed':passed} for name,passed in checks],
        'stored_events':restored.repository.count(),
        'note':'Prueba de lógica, degradación y persistencia con datos ficticios; no demuestra exactitud física.',
    }
    (out/'RELEASE_ACCEPTANCE.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'scenario_matrix.csv').open('w',newline='',encoding='utf-8-sig') as handle:
        writer=csv.DictWriter(handle,fieldnames=['scenario','wbgt_status','review_state','quality_status','simulated'])
        writer.writeheader()
        for name,value in evidence.items():
            writer.writerow({'scenario':name,'wbgt_status':value['environmental_estimator_v18']['status'],
                'review_state':value['review_state_v23']['state'],
                'quality_status':value['engineering_quality_v19']['status'],
                'simulated':value['provenance_summary']['simulated']})
    if report['status'] != 'passed':
        failed=[name for name,passed in checks if not passed]
        raise RuntimeError(f'Falló aceptación v0.30: {failed}')
    return report
