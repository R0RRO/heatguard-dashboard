"""Proveedor meteorológico opcional: pronóstico Open-Meteo, no sensores de faena.

Usa una serie HORARIA UTC y el último registro disponible <= hora del evento.
Conserva fecha, altura y agregación: nunca describe la meteorología regional
como radiación o viento MEDIDOS al lado de un trabajador.
"""
from __future__ import annotations

import copy
import json
import time
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .schema import Observation, iso_datetime

BASE_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARS = (
    "temperature_2m", "relative_humidity_2m", "surface_pressure",
    "wind_speed_10m", "shortwave_radiation",
)
# Nombre en Open-Meteo -> nombre/unit de HeatGuard; observaciones externas.
MAPPING = {
    "temperature_2m": ("air_temperature_c", "degC"),
    "relative_humidity_2m": ("relative_humidity_pct", "percent"),
    "surface_pressure": ("pressure_hpa", "hPa"),
    "wind_speed_10m": ("wind_speed_m_s", "m/s"),
    "shortwave_radiation": ("solar_w_m2", "W/m2"),
}
# Solo datos con validez reciente. Estrictamente NO extrapolar el pronóstico.
MAX_LAG_SECONDS = 3600


def build_url(latitude: float, longitude: float) -> str:
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Coordenadas fuera de rango.")
    args = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(HOURLY_VARS),
        "wind_speed_unit": "ms",  # Open-Meteo usa km/h por defecto
        "temperature_unit": "celsius",
        "timezone": "GMT",     # tiempo UTC, sin ambigüedad DST
        "past_days": 1,
        "forecast_days": 2,
    }
    return BASE_URL + "?" + urlencode(args)


def _http_fetch(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "HeatGuardResearchPrototype/0.2"})
    with urlopen(request, timeout=8) as response:
        return json.load(response)


def parse_openmeteo(data: dict, event_timestamp: str, *, max_lag_s: int = MAX_LAG_SECONDS) -> list[dict]:
    """Devuelve observaciones que cumplen el contrato HeatGuard.

    No interpola ni inventa variables. `shortwave_radiation` es el promedio
    de la hora PRECEDENTE; viento 10 m, temperatura 2 m, presión superficial.
    """
    if not isinstance(data, dict) or not isinstance(data.get("hourly"), dict):
        raise ValueError("La respuesta meteorológica no contiene hourly.")
    hourly = data["hourly"]
    times = hourly.get("time", [])
    target = iso_datetime(event_timestamp).astimezone(timezone.utc)
    candidate = None
    for j, raw in enumerate(times):
        try:
            # timezone=GMT: un tiempo sin sufijo es UTC, no hora local
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age = (target - dt.astimezone(timezone.utc)).total_seconds()
            if 0 <= age <= max_lag_s and (candidate is None or dt > candidate[1]):
                candidate = (j, dt)
        except ValueError:
            continue
    if candidate is None:
        raise ValueError("Sin registro horario meteorológico previo reciente para ese evento.")
    idx, stamp = candidate
    obs = []
    for key, (parameter, unit) in MAPPING.items():
        series = hourly.get(key)
        if not isinstance(series, list) or idx >= len(series) or series[idx] is None:
            continue
        metadata = {
            "origin": "gridded_forecast_model_not_site_measurement",
            "api_field": key,
            "height_m": 10 if key == "wind_speed_10m" else 2 if key in ("temperature_2m", "relative_humidity_2m") else None,
            "temporal_mean": "preceding_1h" if key == "shortwave_radiation" else "hourly_valid_time",
            "note": "No representa necesariamente la condición dentro de la faena ni el flujo relativo al trabajador.",
        }
        obj = {
            "parameter": parameter, "value": series[idx], "unit": unit,
            "kind": "external", "source": "OPEN_METEO_HOURLY_MODEL",
            "timestamp": stamp.isoformat(), "metadata": metadata,
        }
        # Validación de rango/unidades idéntica al núcleo.
        obs.append(Observation.from_dict(obj).as_dict())
    return obs


class WeatherProvider:
    """Cache de la respuesta regional. Reutilizable entre clips en una misma faena."""

    def __init__(self, fetch: Callable[[str], dict] = _http_fetch, ttl_s: int = 1800):
        self.fetch = fetch
        self.ttl_s = ttl_s
        self.cache: dict[tuple[float, float], tuple[float, dict]] = {}

    def _response(self, lat: float, lon: float) -> dict:
        # Redondear para evitar consultas repetidas por pequeñas variaciones GPS.
        key = (round(lat, 3), round(lon, 3))
        now = time.monotonic()
        if key not in self.cache or now - self.cache[key][0] >= self.ttl_s:
            self.cache[key] = (now, self.fetch(build_url(*key)))
        return self.cache[key][1]

    def enrich(self, payload: dict) -> tuple[dict, list[str]]:
        """Solo añade observaciones, no reemplaza las existentes ni presupone seguridad."""
        obj = copy.deepcopy(payload)
        warnings = []
        context = obj.get("context", {})
        if context.get("environment") != "outdoor":
            return obj, ["Meteorología exterior omitida: ambiente no declarado como outdoor."]
        location = context.get("location", {})
        if not isinstance(location, dict):
            return obj, ["Sin localización para solicitar contexto meteorológico."]
        try:
            lat = float(location["latitude_deg"])
            lon = float(location["longitude_deg"])
            data = self._response(lat, lon)
            extra = parse_openmeteo(data, obj["timestamp"])
            existing = obj.setdefault("observations", [])
            # Si el dato externo/modelado va a sustituir un supuesto, la altura
            # del viento (10 m) y el promedio horario (radiación) son los de
            # Open-Meteo, no los del sensor hipotético original.
            use_meteo_wind = not any(x.get("parameter") == "wind_speed_m_s" and
                                      x.get("kind") in ("measured", "external") for x in existing)
            use_meteo_solar = not any(x.get("parameter") == "solar_w_m2" and
                                       x.get("kind") in ("measured", "external") for x in existing)
            existing.extend(extra)
            warnings.append(
                "Se añadieron valores regionales de MODELO meteorológico Open-Meteo; "
                "viento a 10 m y radiación solar horaria NO son mediciones del puesto."
            )
            # Parametrización exigida por lwbgt. No modificar metadatos del usuario.
            weather_model = context.setdefault("weather_model", {})
            if use_meteo_wind:
                weather_model["wind_height_m"] = 10.0
            if use_meteo_solar:
                weather_model["averaging_minutes"] = 60
            # `urban` y gradiente térmico quedan EXPLÍCITOS; si faltan, no calcular lwbgt.
        except (ValueError, KeyError, TypeError, OSError, TimeoutError, json.JSONDecodeError) as exc:
            warnings.append(f"Meteorología no incorporada: {exc}")
        return obj, warnings
