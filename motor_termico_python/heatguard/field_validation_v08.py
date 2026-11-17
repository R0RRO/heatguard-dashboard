"""Validación temporal EXPLORATORIA de un modelo frente a referencias INSTRUMENTALES.

Entradas verificadas manualmente por el investigador. Este software NO acredita
la autenticidad del instrumento, montaje ni cumplimiento ISO.
La calibración se obtiene SOLO de días anteriores a los de evaluación.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
from statistics import mean

from .reference_v07 import compare_to_instrument, read_measured_reference, _metrics


def _finite_sample_conformal_radius(values: list[float], alpha: float) -> float:
    if not values or not (0 < alpha < 1): raise ValueError("Alpha o muestra inválidos")
    ordered = sorted(values)
    k = math.ceil((len(ordered) + 1) * (1-alpha))
    # Si el conjunto es pequeño no hay cota conformal finita de nivel 1-alpha.
    return ordered[k-1] if k <= len(ordered) else float("inf")


def chronological_validation(paired: list[dict], *, alpha: float = .10,
                             train_fraction: float = .70, min_train: int = 10,
                             min_test: int = 5) -> dict:
    if not .5 <= train_fraction <= .85: raise ValueError("train_fraction debe estar en [0.5,0.85]")
    if not 0 < alpha < 1: raise ValueError("alpha inválido")
    dates = sorted(set(p["timestamp_utc"][:10] for p in paired))
    if len(dates) < 4:
        return {"status": "insufficient_independent_days", "n_days": len(dates), "n_pairs": len(paired),
                "note": "Se necesitan >= 4 días para calibrar y evaluar en días completos separados"}
    cut = min(len(dates)-1, max(1, int(len(dates)*train_fraction)))
    train_dates, test_dates = set(dates[:cut]), set(dates[cut:])
    train = [p for p in paired if p["timestamp_utc"][:10] in train_dates]
    test = [p for p in paired if p["timestamp_utc"][:10] in test_dates]
    if len(train) < min_train or len(test) < min_test:
        return {"status": "insufficient_train_or_test_pairs", "n_train": len(train), "n_test": len(test)}
    # e = estimado - observado, restar error medio estimado en días de entrenamiento.
    bias_train = mean(r["error_c"] for r in train)
    residual_train = [abs(r["error_c"]-bias_train) for r in train]
    radius = _finite_sample_conformal_radius(residual_train, alpha)
    corrected_test = [{**r, "error_c": r["error_c"]-bias_train} for r in test]
    coverage = sum(abs(r["error_c"]-bias_train) <= radius for r in test) / len(test)
    by_day = defaultdict(list)
    for r in corrected_test: by_day[r["timestamp_utc"][:10]].append(r)
    return {
        "status": "exploratory_temporal_holdout_completed",
        "research_only": True,
        "model_calibrated_on_past_days_only": True,
        "train_dates": sorted(train_dates), "test_dates": sorted(test_dates),
        "n_train": len(train), "n_test": len(test),
        "bias_calibration_model_minus_instrument_c": round(bias_train, 4),
        "test_uncorrected": _metrics(test),
        "test_bias_corrected": _metrics(corrected_test),
        "alpha_nominal": alpha,
        "calibration_absolute_residual_radius_c": (round(radius, 4) if math.isfinite(radius) else None),
        "test_empirical_coverage": round(coverage, 4),
        "test_metrics_by_date": {k: _metrics(v) for k, v in sorted(by_day.items())},
        "interpretation": "Cobertura empírica a posteriori, no garantía de cobertura en otras faenas ni personas",
        "critical_limitations": [
            "El origen instrumental requiere auditoría manual; el software no verifica calibración o certificación.",
            "El split por días reduce filtración de información temporal pero días cercanos pueden compartir patrones meteorológicos.",
            "La calibración y cobertura no son extrapolables a otras regiones/estaciones o entornos industriales.",
            "No se valida un clip HeatGuard sin comparaciones simultáneas con su hardware.",
            "Conformal requiere intercambiabilidad para cobertura nominal; clima no estacionario y series temporales pueden violarla.",
        ],
    }


def evaluate_model_report(model_report: dict, refs: list[dict], *, site_id: str,
                          max_distance_km: float = 1.0, alpha: float = .10) -> dict:
    matched = compare_to_instrument(model_report, refs, model_site_id=site_id,
                                    max_spatial_separation_km=max_distance_km)
    return {"version": "0.8.0", "source": "independent_instrument_declared_unverified",
            "pairing": {k: matched[k] for k in ("model", "matched", "skipped_distance", "max_separation_km", "all", "day", "night")},
            "temporal_holdout": chronological_validation(matched["pairs"], alpha=alpha),
            "scientific_status": "EXPLORATORY_REGIONAL_COMPARISON_NOT_CLIP_VALIDATION",
            "unverified_provenance": True, "compliance_iso_7243": False,
            "limitations": matched["limitations"]}


def main() -> None:
    p = argparse.ArgumentParser(description="Separación temporal de validación WBGT instrumental independiente")
    p.add_argument("--model-report", required=True)
    p.add_argument("--measured-reference", required=True)
    p.add_argument("--site-id", required=True)
    p.add_argument("--max-distance-km", type=float, default=1.0)
    p.add_argument("--alpha", type=float, default=.10)
    p.add_argument("--out", default="results/field_validation_v08.json")
    a = p.parse_args()
    model = json.loads(Path(a.model_report).read_text(encoding="utf-8"))
    refs = read_measured_reference(a.measured_reference)
    result = evaluate_model_report(model, refs, site_id=a.site_id,
                                   max_distance_km=a.max_distance_km, alpha=a.alpha)
    target = Path(a.out); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Pares instrumentales declarados:", result["pairing"]["matched"])
    print("MAE sin corrección:", result["pairing"]["all"]["mae_c"])
    print("Holdout:", result["temporal_holdout"]["status"])
    print("ADVERTENCIA: origen instrumental no comprobable por el código; no demuestra ISO ni exactitud del clip")


if __name__ == "__main__":
    main()
