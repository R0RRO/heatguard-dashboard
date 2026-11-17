"""Adaptador opcional para lwbgt (modelo físico Liljegren, exteriores).

Se invoca SOLO si se reciben o suponen EXPLÍCITAMENTE todas las entradas
meteorológicas y metadatos requeridos. No se inventan viento ni radiación.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any


MODEL_REQUIRED = ("air_temperature_c", "relative_humidity_pct", "solar_w_m2", "wind_speed_m_s", "pressure_hpa")
LOCATION_REQUIRED = ("latitude_deg", "longitude_deg", "utc_offset_hours")
CONFIG_REQUIRED = ("wind_height_m", "averaging_minutes", "urban", "vertical_temperature_difference_c")


def calculate_optional(values: dict[str, float], timestamp: str, context: dict[str, Any]) -> dict[str, Any]:
    missing = [k for k in MODEL_REQUIRED if k not in values]
    location = context.get("location", {})
    configuration = context.get("weather_model", {})
    if not isinstance(location, dict) or not isinstance(configuration, dict):
        return {"status": "missing_metadata", "missing": ["context.location/weather_model"]}
    missing += [f"context.location.{k}" for k in LOCATION_REQUIRED if k not in location]
    missing += [f"context.weather_model.{k}" for k in CONFIG_REQUIRED if k not in configuration]
    if missing:
        return {"status": "missing_inputs", "missing": missing}
    if context.get("environment") != "outdoor":
        return {"status": "not_applicable", "details": "Liljegren está configurado solo para ambientes exteriores; indicar context.environment=outdoor explícitamente."}

    try:
        from lwbgt import Input, calculate
    except ImportError:
        return {
            "status": "dependency_unavailable",
            "install": "python -m pip install -e '.[wbgt]'",
            "missing": [],
        }
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            return {"status": "invalid_timestamp", "details": "La fecha necesita zona horaria explícita (UTC/Z u offset ISO8601)."}
        offset = float(location["utc_offset_hours"])
        if not isfinite(offset) or not -12 <= offset <= 14:
            return {"status": "invalid_metadata", "details": "utc_offset_hours debe ser un número finito entre -12 y +14."}
        # lwbgt.Input.gmt_offset_hours es un INT32 en la ABI, no double.
        # Antes se entregaba float(9) o float(-3) y ctypes fallaba antes del cálculo.
        # Para zonas no enteras (p. ej. +05:30), se preserva el instante UTC:
        # hora UTC y offset=0 representan el mismo instante solar sin redondear.
        if offset.is_integer():
            gmt_offset = int(offset)
            local = dt.astimezone(timezone(timedelta(hours=gmt_offset)))
        else:
            gmt_offset = 0
            local = dt.astimezone(timezone.utc)
        weather = Input(
            year=local.year, month=local.month, day=local.day,
            hour=local.hour, minute=local.minute,
            gmt_offset_hours=gmt_offset,
            averaging_minutes=int(configuration["averaging_minutes"]),
            urban=int(configuration["urban"]),
            latitude_deg_north=float(location["latitude_deg"]),
            longitude_deg_east=float(location["longitude_deg"]),
            solar_w_m2=values["solar_w_m2"],
            pressure_hpa=values["pressure_hpa"],
            air_temperature_c=values["air_temperature_c"],
            relative_humidity_percent=values["relative_humidity_pct"],
            wind_speed_m_s=values["wind_speed_m_s"],
            wind_height_m=float(configuration["wind_height_m"]),
            vertical_temperature_difference_c=float(configuration["vertical_temperature_difference_c"]),
        )
        result = calculate(weather)
        if result.status != 0:
            return {"status": "model_error", "details": f"lwbgt status={result.status}"}
        return {
            "status": "computed",
            "value_c": round(float(result.wbgt_c), 2),
            "model": "Liljegren via lwbgt; exterior; no equivale a medición ISO",
        }
    except (ValueError, TypeError, OverflowError, RuntimeError) as exc:
        return {"status": "model_error", "details": str(exc)}
