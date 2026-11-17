"""Ejemplo reproducible de un turno SIMULADO, con pausas y hueco de conexión.

Ejecutar desde raíz: python -m scripts.demo_v22_exposure --out results/demo_v22
"""
import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from heatguard.fleet import FleetService
from heatguard.virtual_site import SITE_EXAMPLE, simulated_events


def run(out: Path):
    out.mkdir(parents=True,exist_ok=True)
    db=out/'laboratory.sqlite'
    if db.exists():db.unlink()
    service=FleetService(str(db),scenario=SITE_EXAMPLE)
    rows=[]
    for frame,e in enumerate(simulated_events(devices=3,frames=46,interval_s=120,
                start=datetime(2026,11,15,12,0,tzinfo=timezone.utc))):
        slot=frame//3
        if 20 <= slot < 26:  # 12 minutos sin notificaciones: NO imputar como tiempo medido
            continue
        e['context']['research_review']={'enabled':True,'threshold_c':28,
            'illustrative_half_width_c':1.5,'duration_review_min':10,
            'origin':'RESEARCH_DEMONSTRATION_NOT_LIMIT'}
        e['context']['activity_class']='resting' if slot>=32 else 'moderate'
        e['context']['activity_source']='explicitly_virtual_scenario'
        e['context']['radiation']={'mode':'differential',
            'black_surface_c':37 if e['context']['zone_id']=='exterior_sol' else 31,
            'white_surface_c':30,'source_kind':'assumed','source_id':'SIMULATED_FUTURE_SENSOR'}
        r=service.ingest(e,use_scenario=True)
        if not r.get('accepted'):continue
        result=r['result'];w=result['environmental_estimator_v18'];t=result['exposure_timeline_v22'];band=result['decision_support_v22']
        rows.append({'device_id':e['device_id'],'timestamp':e['timestamp'],
             'simulated':True,'estimated_wbgt_c':w.get('value_c'),
             'review_status':band.get('status'),
             'research_crossover_minutes':t.get('minutes_possible_ge_research_threshold'),
             'covered_min_last_hour':t.get('covered_minutes'),
             'missing_min_last_hour':t.get('missing_minutes'),
             'declared_rest_min_last_hour':t.get('minutes_declared_rest'),
             'battery_pct':result['inputs_selected'].get('battery_level_pct',{}).get('value'),
             'steps_since_boot':result['inputs_selected'].get('steps_since_boot',{}).get('value'),
             'radiative_delta_c':result['inputs_selected'].get('radiative_delta_c',{}).get('value')})
    with (out/'timeline.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    final=service.fleet_summary()
    report={'simulation_only':True,'reference_wbgt_used':False,
            'automatic_occupational_safety_alerts_enabled':False,
            'sample_interval_seconds':120,'missing_slots':[20,21,22,23,24,25],
            'rows_stored':len(rows),'fleet_summary':final}
    (out/'RESULTADO_DEMO.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',default='results/demo_v22')
    args=ap.parse_args()
    r=run(Path(args.out))
    print(json.dumps({'status':'ok','events':r['rows_stored'],
          'simulation_only':True,'results_path':str(args.out),
          'occupational_alerts_enabled':False},ensure_ascii=False,indent=2))
