"""Comparación exploratoria contra WBGT medido e independiente.

Un CSV arbitrario con 'measured_instrument' NO verifica por sí solo autenticidad,
calibración, representatividad espacial o conformidad ISO. No se usan datos
meteorológicos ni otras predicciones como si fueran etiquetas observadas.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import mean
from .sensitivity import quantile
from .weather_history_v07 import _iso_utc

REF_COLUMNS = ("timestamp_utc", "site_id", "instrument_id", "reference_origin", "wbgt_reference_c",
               "latitude_deg", "longitude_deg", "measurement_protocol")


def read_measured_reference(path: str | Path) -> list[dict]:
    result = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        if not r.fieldnames or not set(REF_COLUMNS).issubset(r.fieldnames):
            raise ValueError(f"Referencia exige columnas {REF_COLUMNS}")
        seen = set()
        for n, row in enumerate(r, 2):
            if row["reference_origin"] != "measured_instrument":
                raise ValueError(f"Fila {n}: reference_origin debe ser measured_instrument, no estimado")
            if not row["instrument_id"] or not row["site_id"] or not row["measurement_protocol"]:
                raise ValueError(f"Fila {n}: identificación/protocolo incompleto")
            stamp = _iso_utc(row["timestamp_utc"])
            if stamp in seen: raise ValueError(f"Hora de referencia duplicada {stamp}")
            seen.add(stamp)
            wbgt = float(row["wbgt_reference_c"])
            lat, lon = float(row["latitude_deg"]), float(row["longitude_deg"])
            if not (math.isfinite(wbgt) and -40 <= wbgt <= 80 and -90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError(f"Fila {n}: dato no plausible")
            result.append({**row, "timestamp_utc": stamp, "wbgt_reference_c": wbgt,
                           "latitude_deg": lat, "longitude_deg": lon})
    if not result: raise ValueError("Referencia medida vacía")
    return result


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    a, b, c, d = map(math.radians, (lat1, lon1, lat2, lon2))
    expr = math.sin((c-a)/2)**2 + math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return radius * 2 * math.atan2(math.sqrt(expr), math.sqrt(1-expr))


def _metrics(predictions: list[dict]) -> dict:
    errors = [r["error_c"] for r in predictions]
    if not errors: raise ValueError("No hay pares")
    ae = [abs(e) for e in errors]
    return {"n": len(errors), "mae_c": round(mean(ae), 4),
            "rmse_c": round(math.sqrt(mean([e*e for e in errors])), 4),
            "bias_model_minus_measured_c": round(mean(errors), 4),
            "p90_absolute_error_c": round(quantile(ae, .9), 4),
            "max_abs_error_c": round(max(ae), 4)}


def compare_to_instrument(report: dict, references: list[dict], *, model_site_id: str,
                          max_spatial_separation_km: float = 1.0) -> dict:
    """Devuelve estadísticos descriptivos exploratorios, no conformidad ISO.

    Requiere que el investigador seleccione un sitio y límites espaciales.
    Nunca interpola timestamps, ni fabrica referencias para horas ausentes.
    """
    if not model_site_id.strip(): raise ValueError("model_site_id obligatorio")
    if not 0 <= max_spatial_separation_km <= 100:
        raise ValueError("Separación espacial fuera de rango")
    if not report.get("predictions"):
        raise ValueError("Informe del modelo vacío")
    by_t = {r["timestamp_utc"]: r for r in report["predictions"]}
    paired = []
    skipped_spatial = 0
    for ref in references:
        if ref["site_id"] != model_site_id:
            continue
        sample = by_t.get(ref["timestamp_utc"])
        if sample is None: continue
        if sample.get("data_origin") == "synthetic_fixture":
            raise ValueError("Prohibido declarar exactitud utilizando fixture meteorológico sintético")
        # Aun a 0 metros, el reanálisis regional puede diferir de un instrumento in situ.
        lat = float(sample["latitude_deg"])
        lon = float(sample["longitude_deg"])
        distance = _haversine_km(lat, lon, ref["latitude_deg"], ref["longitude_deg"])
        if distance > max_spatial_separation_km:
            skipped_spatial += 1
            continue
        if ref["reference_origin"] != "measured_instrument":
            raise ValueError("WBGT de referencia no instrumental")
        prediction = float(sample["baseline_full_external"])
        paired.append({"timestamp_utc": sample["timestamp_utc"], "instrument_id": ref["instrument_id"],
                       "site_id": model_site_id, "reference_c": ref["wbgt_reference_c"],
                       "model_c": prediction, "error_c": prediction - ref["wbgt_reference_c"],
                       "separation_km": round(distance, 4),
                       "solar_w_m2": sample["solar_w_m2"],
                       "meteorology_origin": sample["data_origin"]})
    if not paired:
        raise ValueError("Sin pares coincidentes exactos en UTC/espacio; no se generaron métricas")
    day = [r for r in paired if r["solar_w_m2"] > 20]
    night = [r for r in paired if r["solar_w_m2"] <= 20]
    return {"research_only": True, "measurement_reference_declared": "measured_instrument",
            "reference_authenticity_verified_by_code": False,
            "safety_certification": False, "model": report["model"],
            "interpretation": "Comparación regional exploratoria, NO calibración de clip ni validación normativa",
            "model_site_id": model_site_id, "matched": len(paired),
            "skipped_distance": skipped_spatial,
            "max_separation_km": max_spatial_separation_km,
            "all": _metrics(paired), "day": _metrics(day) if day else None,
            "night": _metrics(night) if night else None, "pairs": paired,
            "limitations": [
                "El archivo CSV y reference_origin son declarados por el investigador: auditar origen y protocolo manualmente.",
                "Coincidencia de hora y distancia NO garantiza mismas radiaciones, alturas ni exposición espacial.",
                "Los modelos de reanálisis no reproducen necesariamente fuentes radiantes industriales.",
                "No se valida el dispositivo HeatGuard físico, pues los datos del clip no están presentes.",
            ]}


def main() -> None:
    p = argparse.ArgumentParser(description="Comparación exploratoria contra WBGT INSTRUMENTAL, CSV externo obligatorio")
    p.add_argument("--model-report", required=True)
    p.add_argument("--measured-reference", required=True)
    p.add_argument("--site-id", required=True)
    p.add_argument("--max-distance-km", type=float, default=1)
    p.add_argument("--out", default="results/reference_comparison.json")
    args = p.parse_args()
    report = json.loads(Path(args.model_report).read_text(encoding="utf-8"))
    # El reporte debe preservar latitudes del archivo inicial.
    result = compare_to_instrument(report, read_measured_reference(args.measured_reference),
                                   model_site_id=args.site_id, max_spatial_separation_km=args.max_distance_km)
    dest = Path(args.out); dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{result['matched']} pares instrumentales declarados; MAE exploratorio {result['all']['mae_c']} °C")
    print("ADVERTENCIA: verificación de origen, proximidad y metodología aún requerida.")


if __name__ == "__main__":
    main()
