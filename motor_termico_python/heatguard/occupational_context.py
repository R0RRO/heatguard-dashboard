"""Independent occupational context model.

The clip measures environmental variables.  Workload, clothing and
acclimatization are separate declarations and are never inferred from steps or
accelerometer magnitude.  This module validates and exposes that distinction;
it does not implement a legal exposure limit.
"""
from __future__ import annotations

from math import isfinite
from typing import Any


ACTIVITY_CLASSES = {"resting", "light", "moderate", "heavy", "very_heavy", "unknown"}
ACCLIMATIZATION_STATES = {"acclimatized", "not_acclimatized", "in_progress", "unknown"}
WORK_STATES = {"working", "resting", "break", "off_shift", "unknown"}


def _optional_number(value: Any, name: str, low: float, high: float) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"context.{name} debe ser numérico")
    number = float(value)
    if not isfinite(number) or not low <= number <= high:
        raise ValueError(f"context.{name} fuera de rango [{low}, {high}]")
    return number


def evaluate_occupational_context(context: dict[str, Any], estimate: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(context, dict):
        raise ValueError("context debe ser objeto")
    activity = str(context.get("activity_class", "unknown"))
    if activity not in ACTIVITY_CLASSES:
        raise ValueError(f"context.activity_class no reconocido: {activity!r}")
    acclimatization = str(context.get("acclimatization", "unknown"))
    if acclimatization not in ACCLIMATIZATION_STATES:
        raise ValueError(f"context.acclimatization no reconocido: {acclimatization!r}")
    work_state = str(context.get("work_state", "unknown"))
    if work_state not in WORK_STATES:
        raise ValueError(f"context.work_state no reconocido: {work_state!r}")

    metabolic_w = _optional_number(context.get("metabolic_rate_w"), "metabolic_rate_w", 40, 1000)
    metabolic_source = context.get("metabolic_rate_source")
    if metabolic_w is not None and (not isinstance(metabolic_source, str) or not metabolic_source.strip()):
        raise ValueError("context.metabolic_rate_source es obligatorio al declarar metabolic_rate_w")

    clothing = context.get("clothing", "unknown")
    if isinstance(clothing, str):
        ensemble = clothing.strip() or "unknown"
        clothing_adjustment_c = None
        clothing_source = "not_declared"
    elif isinstance(clothing, dict):
        ensemble = str(clothing.get("ensemble", "unknown")).strip() or "unknown"
        clothing_adjustment_c = _optional_number(
            clothing.get("adjustment_c"), "clothing.adjustment_c", -5, 20
        )
        clothing_source = str(clothing.get("source", "not_declared")).strip()
        if clothing_adjustment_c is not None and clothing_source in ("", "not_declared"):
            raise ValueError("context.clothing.source es obligatorio al declarar adjustment_c")
    else:
        raise ValueError("context.clothing debe ser texto u objeto")

    central = estimate.get("value_c") if estimate.get("status") == "computed" else None
    adjusted = None
    if central is not None and clothing_adjustment_c is not None:
        adjusted = round(float(central) + clothing_adjustment_c, 3)

    declared = {
        "activity": activity != "unknown",
        "metabolic_rate": metabolic_w is not None,
        "clothing": ensemble != "unknown",
        "clothing_adjustment": clothing_adjustment_c is not None,
        "acclimatization": acclimatization != "unknown",
        "work_state": work_state != "unknown",
    }
    missing = [name for name in ("activity", "clothing", "acclimatization") if not declared[name]]
    return {
        "activity_class": activity,
        "activity_source": context.get("activity_source", "not_declared"),
        "metabolic_rate_w": metabolic_w,
        "metabolic_rate_source": metabolic_source or "not_declared",
        "metabolic_rate_inferred_from_steps": False,
        "clothing_ensemble": ensemble,
        "clothing_adjustment_c": clothing_adjustment_c,
        "clothing_adjustment_source": clothing_source,
        "acclimatization": acclimatization,
        "work_state": work_state,
        "declared_fields": declared,
        "missing_for_professional_interpretation": missing,
        "context_completeness_fraction": round(sum(declared.values()) / len(declared), 3),
        "environmental_estimate_c": central,
        "clothing_adjusted_research_value_c": adjusted,
        "adjusted_value_is_not_a_legal_limit": True,
        "normative_assessment_performed": False,
        "automatic_safety_decision": False,
        "interpretation": (
            "Contexto independiente y declarado. Pasos/movimiento no determinan por sí solos "
            "la carga metabólica; la evaluación ocupacional requiere método y profesional competente."
        ),
    }
