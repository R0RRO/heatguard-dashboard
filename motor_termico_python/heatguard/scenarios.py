"""Hipótesis EXPLÍCITAS para desarrollo sin anemómetro/radiómetro.

Nunca asigna una hipótesis si ya existe observación de ese parámetro.
La fuente de cada dato se etiqueta; no son mediciones ni cumplen ISO.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
from dataclasses import dataclass
from .schema import Observation, iso_datetime


@dataclass(frozen=True)
class SiteScenario:
    site_id: str
    latitude_deg: float
    longitude_deg: float
    utc_offset_hours: float
    assumed_wind_m_s: float = 1.0
    assumed_solar_w_m2: float = 500.0
    assumed_pressure_hpa: float = 1013.25
    urban: int = 1
    vertical_temperature_difference_c: float = 0.0
    # Estos valores son hipótesis configurables para simular, NO defaults clínicos.

    @classmethod
    def from_dict(cls, value: dict) -> 'SiteScenario':
        return cls(**value)


def apply_explicit_scenario(event: dict, scenario: SiteScenario | None, *, enabled: bool = False) -> dict:
    """Enriquece un evento para escenario exterior, sin suplantar datos medidos.

    Si enabled=False, no rellena nada. Devuelve copia.
    """
    obj = copy.deepcopy(event)
    if not enabled or scenario is None:
        return obj
    context = obj.setdefault('context', {})
    if context.get('environment') != 'outdoor':
        return obj
    iso_datetime(obj['timestamp'])
    context.setdefault('site_id', scenario.site_id)
    context.setdefault('location', {
        'latitude_deg': scenario.latitude_deg,
        'longitude_deg': scenario.longitude_deg,
        'utc_offset_hours': scenario.utc_offset_hours,
    })
    weather = context.setdefault('weather_model', {})
    for k, v in {
        'wind_height_m': 10.0, 'averaging_minutes': 60,
        'urban': scenario.urban,
        'vertical_temperature_difference_c': scenario.vertical_temperature_difference_c,
    }.items():
        weather.setdefault(k, v)
    existing = {o['parameter'] for o in obj.get('observations', [])}
    values = {
        'wind_speed_m_s': (scenario.assumed_wind_m_s, 'm/s'),
        'solar_w_m2': (scenario.assumed_solar_w_m2, 'W/m2'),
        'pressure_hpa': (scenario.assumed_pressure_hpa, 'hPa'),
    }
    readings = obj.setdefault('observations', [])
    for key, (value, unit) in values.items():
        if key not in existing:
            readings.append(Observation.from_dict({
                'parameter': key, 'value': value, 'unit': unit, 'kind': 'assumed',
                'source': 'EXPLICIT_SCENARIO_NOT_SENSOR', 'timestamp': obj['timestamp'],
                'metadata': {'site_id': scenario.site_id, 'simulated': True,
                             'why': 'Falta sensor local; supuesto para análisis exploratorio'},
            }).as_dict())
    obj.setdefault('transport_metadata', {})['scenario_enriched'] = True
    return obj


def load_scenario(filename: str | None, fallback: SiteScenario) -> SiteScenario:
    if not filename:
        return fallback
    return SiteScenario.from_dict(json.loads(Path(filename).read_text(encoding='utf-8')))
