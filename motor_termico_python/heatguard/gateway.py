"""Adaptador de pasarela móvil: añade datos opcionables del teléfono y wearable.

No llama a Health Connect/HealthKit ni accede al móvil por sí mismo.
Recibe datos ya autorizados de una futura aplicación móvil.
"""
from __future__ import annotations
import copy
from .schema import Observation, read_event


def append_gateway_sources(event: dict, *, phone: dict | None = None,
                           wearable: dict | None = None) -> dict:
    obj = copy.deepcopy(event)
    ctx = obj.setdefault('context', {})
    observed = obj.setdefault('observations', [])
    timestamp = obj['timestamp']

    def add(parameter: str, value: float, unit: str, source: str):
        observed.append(Observation.from_dict({
            'parameter': parameter, 'value': value, 'unit': unit,
            'kind': 'external', 'source': source, 'timestamp': timestamp,
            'metadata': {'received_through': 'mobile_gateway', 'quality': 'not_independently_validated'},
        }).as_dict())

    if phone:
        if phone.get('location_consent') is True:
            ctx['location_consent'] = True
            mapping = {'latitude_deg': ('gps_latitude_deg', 'deg'),
                       'longitude_deg': ('gps_longitude_deg', 'deg'),
                       'speed_m_s': ('gps_speed_m_s', 'm/s')}
            for key, (param, unit) in mapping.items():
                if phone.get(key) is not None:
                    add(param, phone[key], unit, 'PHONE_GPS_OPTIONAL')
    if wearable:
        if wearable.get('physiology_consent') is True:
            ctx['physiology_consent'] = True
            if wearable.get('heart_rate_bpm') is not None:
                add('heart_rate_bpm', wearable['heart_rate_bpm'], 'bpm',
                    'OPTIONAL_WEARABLE_NOT_DIAGNOSTIC')
    read_event(obj)
    return obj
