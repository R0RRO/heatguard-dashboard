"""Red de clips: respaldo solo para T y HR, con misma zona y ventana temporal.

El consenso evita mezclar exposiciones diferentes y no sustituye calibración.
"""
from __future__ import annotations
from datetime import datetime
from statistics import median
from .schema import Observation, iso_datetime

PARAMS = {'air_temperature_c': ('degC', 3.0), 'relative_humidity_pct': ('percent', 12.0)}


def neighbor_candidates(event: dict, latest_events: dict[str, dict], *, max_age_s=30,
                        min_peers=2) -> list[dict]:
    zone = event.get('context', {}).get('zone_id')
    target = iso_datetime(event['timestamp'])
    own = {o['parameter'] for o in event.get('observations', [])}
    output = []
    for parameter, (unit, max_spread) in PARAMS.items():
        if parameter in own:
            continue
        peers: list[tuple[str, float, bool]] = []
        for device_id, old in latest_events.items():
            if device_id == event['device_id'] or old.get('context', {}).get('zone_id') != zone:
                continue
            age = (target - iso_datetime(old['timestamp'])).total_seconds()
            if age < 0 or age > max_age_s:
                continue
            for obs in old.get('observations', []):
                if obs.get('parameter') == parameter and obs.get('kind') in ('measured', 'assumed'):
                    peers.append((device_id, float(obs['value']),
                                  old.get('transport_metadata', {}).get('simulated', False) or obs['kind'] == 'assumed'))
                    break
        if len(peers) < min_peers:
            continue
        values = [p[1] for p in peers]
        if max(values) - min(values) > max_spread:
            continue
        output.append(Observation.from_dict({
            'parameter': parameter, 'value': median(values), 'unit': unit,
            'source': 'NEIGHBOR_ZONE_MEDIAN_UNVALIDATED', 'kind': 'neighbor',
            'zone_id': zone, 'timestamp': event['timestamp'],
            'metadata': {'devices': [p[0] for p in peers], 'peer_count': len(peers),
                         'all_peers_simulated': all(p[2] for p in peers),
                         'warning': 'Misma zona no garantiza mismo ambiente'},
        }).as_dict())
    return output
