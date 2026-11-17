"""Series meteorológicas históricas para investigación (NO WBGT observado).

Open-Meteo Historical Weather usa reanálisis meteorológico; su GHI promedio
horario y viento 10m no describen necesariamente la zona de cada trabajador.
A diferencia de weather.py (pronóstico), este módulo trae *históricos*.
No descarga nada hasta usar explícitamente `--download`.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, date, timezone
import json
import math
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

URL = "https://archive-api.open-meteo.com/v1/archive"
VARS = (
    "temperature_2m", "relative_humidity_2m", "shortwave_radiation",
    "wind_speed_10m", "surface_pressure",
)
CSV_COLUMNS = (
    "timestamp_utc", "air_temperature_c", "relative_humidity_pct",
    "solar_w_m2", "wind_speed_10m_m_s", "pressure_hpa",
    "data_origin", "latitude_deg", "longitude_deg", "solar_averaging_minutes",
    "wind_height_m", "station_or_dataset", "session_id",
)


def history_url(latitude: float, longitude: float, start_date: str, end_date: str) -> str:
    lat, lon = float(latitude), float(longitude)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Coordenadas inválidas")
    a, b = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if a > b or (b - a).days > 366:
        raise ValueError("Fechas inválidas o ventana > 367 días")
    return URL + "?" + urlencode({
        "latitude": lat, "longitude": lon,
        "start_date": start_date, "end_date": end_date,
        "hourly": ",".join(VARS),
        "timezone": "UTC", "wind_speed_unit": "ms",
        "temperature_unit": "celsius", "precipitation_unit": "mm",
    })


def fetch_json(url: str) -> dict:
    if not url.startswith(URL + "?"):
        raise ValueError("Solo se permite la URL del archivo histórico de Open-Meteo")
    req = Request(url, headers={"User-Agent": "HeatGuardScientificResearch/0.7 (education)"})
    with urlopen(req, timeout=25) as resp:
        obj = json.load(resp)
    if obj.get("error"):
        raise ValueError(f"Respuesta meteorológica: {obj.get('reason', 'error')}")
    return obj


def _iso_utc(value: str) -> str:
    """Evita errores por convertir una cadena horaria local a UTC arbitrariamente."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        # La petición exige timezone=UTC, por lo que las cadenas naive son UTC.
        dt = dt.replace(tzinfo=timezone.utc)
    if dt.utcoffset().total_seconds() != 0:
        raise ValueError("El archivo histórico debe venir con timezone UTC")
    return dt.isoformat().replace("+00:00", "Z")


def normalize_openmeteo(obj: dict, *, session_id: str = "om_archive") -> list[dict]:
    if obj.get("timezone") not in ("GMT", "UTC") or int(obj.get("utc_offset_seconds", -1)) != 0:
        raise ValueError("La respuesta debe haber sido solicitada en timezone=UTC")
    hourly = obj.get("hourly", {})
    times = hourly.get("time", [])
    if not isinstance(times, list) or not times:
        raise ValueError("Faltan horas en respuesta de Open-Meteo")
    if any(not isinstance(hourly.get(k), list) or len(hourly[k]) != len(times) for k in VARS):
        raise ValueError("Longitudes diferentes entre variables meteorológicas")
    units = obj.get("hourly_units", {})
    required_units = {
        "temperature_2m": "°C", "relative_humidity_2m": "%",
        "shortwave_radiation": "W/m²", "wind_speed_10m": "m/s",
        "surface_pressure": "hPa",
    }
    for key, unit in required_units.items():
        if units and units.get(key) != unit:
            raise ValueError(f"Unidad inesperada de {key}: {units.get(key)!r} != {unit}")
    rows = []
    seen = set()
    for i, value in enumerate(times):
        measurements = [hourly[k][i] for k in VARS]
        if any(v is None for v in measurements):
            continue  # faltantes no se inventan ni se interpolan
        t, rh, solar, wind, p = map(float, measurements)
        if not all(math.isfinite(v) for v in (t, rh, solar, wind, p)):
            continue
        ts = _iso_utc(value)
        if ts in seen: raise ValueError(f"Hora duplicada: {ts}")
        seen.add(ts)
        row = {
            "timestamp_utc": ts,
            "air_temperature_c": t,
            "relative_humidity_pct": rh,
            "solar_w_m2": solar,
            "wind_speed_10m_m_s": wind,
            "pressure_hpa": p,
            "data_origin": "reanalysis_model",
            "latitude_deg": float(obj["latitude"]),
            "longitude_deg": float(obj["longitude"]),
            "solar_averaging_minutes": 60,
            "wind_height_m": 10,
            "station_or_dataset": "Open-Meteo Historical Weather API / reanalysis",
            "session_id": session_id,
        }
        validate_weather_row(row)
        rows.append(row)
    return rows


def validate_weather_row(row: dict) -> dict:
    missing = set(CSV_COLUMNS).difference(row)
    if missing:
        raise ValueError(f"Columnas faltantes: {sorted(missing)}")
    _iso_utc(str(row["timestamp_utc"]))
    if row["data_origin"] not in {"reanalysis_model", "site_measurement", "synthetic_fixture"}:
        raise ValueError("Origen meteorológico desconocido; no reclasificar a WBGT medido")
    bounds = {
        "air_temperature_c": (-50, 60), "relative_humidity_pct": (0, 100),
        "solar_w_m2": (0, 1600), "wind_speed_10m_m_s": (0, 80),
        "pressure_hpa": (600, 1100), "latitude_deg": (-90, 90),
        "longitude_deg": (-180, 180),
    }
    for k, (lo, hi) in bounds.items():
        n = float(row[k])
        if not math.isfinite(n) or not lo <= n <= hi:
            raise ValueError(f"Dato inválido {k}={row[k]}")
    if float(row["wind_height_m"]) != 10 or float(row["solar_averaging_minutes"]) != 60:
        raise ValueError("Este formato requiere viento 10m y GHI promediada 60 minutos")
    return row


def save_weather_csv(path: str | Path, rows: list[dict]) -> None:
    out = Path(path); out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for row in rows: w.writerow(validate_weather_row(row))


def load_weather_csv(path: str | Path) -> list[dict]:
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        if not r.fieldnames or not set(CSV_COLUMNS).issubset(r.fieldnames):
            raise ValueError("El CSV no corresponde a weather_history_v07: columnas insuficientes")
        rows = [validate_weather_row(dict(x)) for x in r]
    if not rows: raise ValueError("CSV meteorológico vacío")
    stamps = [str(x["timestamp_utc"]) for x in rows]
    if len(stamps) != len(set(stamps)):
        raise ValueError("Timestamps duplicados")
    rows.sort(key=lambda x: x["timestamp_utc"])
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description="Descargar Open-Meteo histórico. Es REANÁLISIS, no WBGT observado.")
    p.add_argument("--latitude", type=float, required=True)
    p.add_argument("--longitude", type=float, required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--out", default="data/openmeteo_history.csv")
    p.add_argument("--download", action="store_true", help="Sin esta bandera NO se accede a internet")
    args = p.parse_args()
    url = history_url(args.latitude, args.longitude, args.start, args.end)
    if not args.download:
        print("URL preparada, descarga desactivada. Añade --download para consultar:")
        print(url)
        return
    rows = normalize_openmeteo(fetch_json(url), session_id=f"om_{args.start}_{args.end}")
    save_weather_csv(args.out, rows)
    print(f"Guardadas {len(rows)} horas meteorológicas REANALIZADAS en {args.out} (no WBGT medido)")


if __name__ == "__main__":
    main()
