"""Conversión de CSV oficial de estación japonesa WBGT INSTRUMENTAL a HeatGuard.

Esta herramienta acepta solo cuando el operador declara expresamente que el
archivo proviene de la categoría 'observación real por estación'. No debe
usarse para un CSV de 'estimación en tiempo real' o pronóstico. El código no
puede comprobar autenticidad de un archivo externo por sí solo.

Formato de prueba: fecha, hora 1..24, WBGT, temperatura de globo (opcional).
La fuente oficial documenta horas 1:00..24:00 y la cuarta columna Tg.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .reference_v07 import REF_COLUMNS


JST = timezone(timedelta(hours=9))


def japanese_date_time(date_str: str, time_str: str) -> str:
    date_clean = date_str.strip()
    day = None
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y%m%d"):
        try:
            day = datetime.strptime(date_clean, fmt)
            break
        except ValueError:
            continue
    if day is None: raise ValueError(f"Fecha japonesa inválida: {date_str}")
    parts = time_str.strip().split(":")
    try:
        hr = int(parts[0])
        minute = int(parts[1]) if len(parts) == 2 else 0
    except ValueError as exc:
        raise ValueError("Hora japonesa inválida") from exc
    if len(parts) > 2 or hr < 1 or hr > 24 or minute != 0:
        raise ValueError("Se esperan horas japonesas 1..24 sin minutos adicionales")
    # '24:00' es medianoche del día SIGUIENTE, no '00:00' del mismo día.
    if hr == 24: day += timedelta(days=1)
    else: day += timedelta(hours=hr)
    return day.replace(tzinfo=JST).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def transform_observed_station_csv(source: str | Path, *, site_id: str,
                                   instrument_id: str, latitude_deg: float, longitude_deg: float,
                                   declared_measured_station: bool = False,
                                   wbgt_column: int = 2) -> list[dict]:
    if not declared_measured_station:
        raise ValueError("Debes declarar explícitamente que el archivo es WBGT INSTRUMENTAL por estación; nunca estimado")
    if not site_id.strip() or not instrument_id.strip():
        raise ValueError("Falta ID de estación/instrumento")
    lat, lon = float(latitude_deg), float(longitude_deg)
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("Coordenadas inválidas")
    if wbgt_column < 2: raise ValueError("La columna WBGT debe ser al menos la tercera")
    result = []
    seen = set()
    with Path(source).open(encoding="utf-8-sig", newline="") as f:
        rows = csv.reader(f)
        for line, row in enumerate(rows, 1):
            if line == 1: continue  # encabezado oficial
            if len(row) <= wbgt_column: continue
            if not row[wbgt_column].strip(): continue  # ausentes explícitos
            try:
                ts = japanese_date_time(row[0], row[1])
                wbgt = float(row[wbgt_column])
            except ValueError as exc:
                raise ValueError(f"Fila {line}: {exc}") from exc
            if not -40 <= wbgt <= 80:
                raise ValueError(f"Fila {line}: WBGT no plausible; verificar unidades y si es observación")
            if ts in seen: raise ValueError(f"Hora duplicada: {ts}")
            seen.add(ts)
            result.append({
                "timestamp_utc": ts, "site_id": site_id,
                "instrument_id": instrument_id,
                "reference_origin": "measured_instrument",
                "wbgt_reference_c": wbgt,
                "latitude_deg": lat, "longitude_deg": lon,
                "measurement_protocol": "Japan MOE station measured WBGT; researcher-declared; verify methods/site",
            })
    if not result: raise ValueError("No se encontraron datos WBGT instrumentales")
    return result


def save_refs(path: str | Path, rows: list[dict]) -> None:
    dest = Path(path); dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REF_COLUMNS, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)


def main() -> None:
    p = argparse.ArgumentParser(description="Convertir archivo japonés WBGT INSTRUMENTAL (no estimaciones)")
    p.add_argument("--source", required=True)
    p.add_argument("--site-id", required=True)
    p.add_argument("--instrument-id", required=True)
    p.add_argument("--latitude", type=float, required=True)
    p.add_argument("--longitude", type=float, required=True)
    p.add_argument("--wbgt-column", type=int, default=2, help="Índice desde cero; 2 = tercera columna")
    p.add_argument("--declared-measured-station", action="store_true")
    p.add_argument("--out", required=True)
    a = p.parse_args()
    records = transform_observed_station_csv(
        a.source, site_id=a.site_id, instrument_id=a.instrument_id,
        latitude_deg=a.latitude, longitude_deg=a.longitude,
        declared_measured_station=a.declared_measured_station,
        wbgt_column=a.wbgt_column,
    )
    save_refs(a.out, records)
    print(f"Convertidos {len(records)} registros, estación {a.site_id} (origen instrumentado DECLARADO, no verificado)")


if __name__ == "__main__":
    main()
