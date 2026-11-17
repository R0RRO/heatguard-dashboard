"""Validación mínima del contrato de datos que envía una fuente a HeatGuard.

Solo los campos enumerados en UNITS participan hoy en el cálculo térmico.
Otras variables (pasos, GPS, frecuencia cardiaca) se conservan sin interpretarlas.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Any


UNITS = {
    "air_temperature_c": "degC",
    "relative_humidity_pct": "percent",
    "solar_w_m2": "W/m2",
    "wind_speed_m_s": "m/s",
    "pressure_hpa": "hPa",
    "activity_rms_g": "g",
    "surface_temperature_c": "degC",
    "radiative_black_surface_c": "degC",
    "radiative_white_surface_c": "degC",
    "radiative_delta_c": "degC",
    "hydration_self_report_count": "count",
    "battery_level_pct": "percent",
    "steps_since_boot": "count",
    "heading_relative_deg": "deg",
    "pitch_deg": "deg",
    "roll_deg": "deg",
    "acceleration_magnitude_g": "g",
    "gps_latitude_deg": "deg",
    "gps_longitude_deg": "deg",
    "gps_speed_m_s": "m/s",
    "heart_rate_bpm": "bpm",
    "globe_reference_c": "degC",
    "natural_wet_bulb_reference_c": "degC",
    "wbgt_reference_c": "degC",
}
# Rangos operacionales de comprobación de entrada, NO rangos normativos.
BOUNDS = {
    "air_temperature_c": (-40.0, 80.0),
    "relative_humidity_pct": (0.0, 100.0),
    "solar_w_m2": (0.0, 2000.0),
    "wind_speed_m_s": (0.0, 45.0),
    "pressure_hpa": (500.0, 1100.0),
    "activity_rms_g": (0.0, 20.0),
    "surface_temperature_c": (-40.0, 110.0),
    "radiative_black_surface_c": (-40.0, 110.0),
    "radiative_white_surface_c": (-40.0, 110.0),
    "radiative_delta_c": (-150.0, 150.0),
    "hydration_self_report_count": (0, 100000),
    "battery_level_pct": (0, 100),
    "steps_since_boot": (0, 4294967295),
    "heading_relative_deg": (0, 360),
    "pitch_deg": (-180, 180),
    "roll_deg": (-180, 180),
    "acceleration_magnitude_g": (0, 20),
    "gps_latitude_deg": (-90, 90),
    "gps_longitude_deg": (-180, 180),
    "gps_speed_m_s": (0, 60),
    "heart_rate_bpm": (20, 250),
    "globe_reference_c": (-40, 120),
    "natural_wet_bulb_reference_c": (-40, 90),
    "wbgt_reference_c": (-40, 90),
}
KINDS = {"measured", "external", "estimated", "assumed", "neighbor"}
QUALITY_LEVELS = {"verified", "good", "unverified", "suspect"}


def iso_datetime(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("La marca de tiempo debe ser una cadena ISO 8601.")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Fecha/hora inválida: {value!r}") from exc
    if dt.tzinfo is None:
        raise ValueError("La fecha/hora debe incluir una zona horaria: Z o ±HH:MM.")
    return dt


@dataclass(frozen=True)
class Observation:
    parameter: str
    value: float
    unit: str
    kind: str
    source: str
    zone_id: str | None = None
    timestamp: str | None = None
    metadata: dict | None = None
    quality: str = "unverified"

    @classmethod
    def from_dict(cls, obj: dict[str, Any]) -> "Observation":
        if not isinstance(obj, dict):
            raise ValueError("Cada observación debe ser un objeto JSON.")
        parameter = str(obj.get("parameter", "")).strip()
        kind = str(obj.get("kind", "")).strip()
        source = str(obj.get("source", "")).strip()
        if not parameter or not source:
            raise ValueError("La observación requiere 'parameter' y 'source'.")
        if kind not in KINDS:
            raise ValueError(f"kind inválido en {parameter}: {kind!r}.")
        try:
            value = float(obj["value"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Valor numérico requerido para {parameter}.") from exc
        if not isfinite(value):
            raise ValueError(f"Valor no finito para {parameter}.")
        unit = str(obj.get("unit", ""))
        if parameter in UNITS:
            if unit != UNITS[parameter]:
                raise ValueError(
                    f"Unidad incorrecta para {parameter}: se requiere {UNITS[parameter]}."
                )
            lo, hi = BOUNDS[parameter]
            if not (lo <= value <= hi):
                raise ValueError(f"{parameter} fuera del rango de comprobación [{lo}, {hi}].")
        elif not unit:
            raise ValueError(f"Indica unit para la nueva variable {parameter}.")
        zone = obj.get("zone_id")
        timestamp = obj.get("timestamp")
        if timestamp is not None:
            iso_datetime(timestamp)
        metadata = obj.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("metadata debe ser un objeto JSON.")
        quality = str(obj.get("quality", "unverified")).strip().lower()
        if quality not in QUALITY_LEVELS:
            raise ValueError(f"quality inválida en {parameter}: {quality!r}.")
        return cls(
            parameter=parameter, value=value, unit=unit,
            kind=kind, source=source, zone_id=zone, timestamp=timestamp, metadata=metadata,
            quality=quality,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter, "value": self.value,
            "unit": self.unit, "kind": self.kind, "source": self.source,
            "zone_id": self.zone_id, "timestamp": self.timestamp,
            "metadata": self.metadata, "quality": self.quality,
        }


def read_event(payload: dict[str, Any]) -> tuple[str, str, str, dict, list[Observation]]:
    if not isinstance(payload, dict):
        raise ValueError("La entrada debe ser un objeto JSON.")
    device_id = str(payload.get("device_id", "")).strip()
    if not device_id:
        raise ValueError("Es obligatorio device_id.")
    timestamp = str(payload.get("timestamp", ""))
    iso_datetime(timestamp)
    context = payload.get("context", {})
    if not isinstance(context, dict):
        raise ValueError("context debe ser un objeto JSON.")
    zone_id = str(context.get("zone_id", "")).strip()
    if not zone_id:
        raise ValueError("Indica context.zone_id (puede ser 'unknown').")
    raws = payload.get("observations", [])
    if not isinstance(raws, list):
        raise ValueError("observations debe ser una lista.")
    readings = [Observation.from_dict(x) for x in raws]
    return device_id, timestamp, zone_id, context, readings


def check_sensitive_ingestion(context: dict, readings: list[Observation]) -> None:
    """Política de PERSISTENCIA: no guardar datos personales sin consentimiento."""
    if any(o.parameter == 'heart_rate_bpm' for o in readings) and context.get('physiology_consent') is not True:
        raise ValueError('heart_rate_bpm requiere context.physiology_consent=true.')
    if any(o.parameter.startswith('gps_') for o in readings) and context.get('location_consent') is not True:
        raise ValueError('Posición GPS individual requiere context.location_consent=true.')
