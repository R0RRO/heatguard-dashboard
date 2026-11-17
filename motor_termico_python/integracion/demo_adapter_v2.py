"""Ejemplo autónomo de compatibilidad con JSON del dashboard. NO conexión automática Node.

Desde motor_termico_python:
    python -m integracion.demo_adapter_v2
"""
from pathlib import Path
import json
from .telemetry_v2_adapter import convert_v2_to_heatguard_event
from heatguard.pipeline import evaluate


def main():
    p=Path(__file__).resolve().parent.parent/'examples'/'telemetry_v2_demo.json'
    payload=json.loads(p.read_text(encoding='utf8'))
    event=convert_v2_to_heatguard_event(payload,zone_id='obra_demo',environment='outdoor',simulated=True)
    result=evaluate(event)
    print(json.dumps({
        'status':'simulated_demo',
        'device_id':event['device_id'],
        'environmental_estimator_v18':result['environmental_estimator_v18'],
        'health_index_auxiliary':result.get('metrics',{}).get('heat_index_c'),
        'note':'Sin radiacion ni viento no se calcula WBGT. Esto no es una alerta ISO.'
    },ensure_ascii=False,indent=2))

if __name__=='__main__':main()
