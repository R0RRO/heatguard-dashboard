"""Selecciona fuentes; NO confunde una hipótesis con una medición.

v0.1: no promedia sensores vecinos; primero valida procedencia y zona.
Más adelante este módulo será el punto para fusionar series temporales y calibraciones.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .schema import Observation, iso_datetime


PRIORITY = {"measured": 0, "external": 1, "estimated": 2, "neighbor": 3, "assumed": 4}
REQUIRED = ("air_temperature_c", "relative_humidity_pct")
PHYSICAL_OPTIONAL = ("solar_w_m2", "wind_speed_m_s", "pressure_hpa")

# Diferencia admitida entre la lectura y el instante del evento. Los límites
# son decisiones iniciales de ingeniería, configurables en una versión futura.
MAX_AGE_S = {"measured": 180, "neighbor": 120, "external": 3600, "estimated": 3600, "assumed": None}


@dataclass
class FusionResult:
    chosen: dict[str, Observation]
    rejected: list[dict]
    warnings: list[str]
    contradictions: list[dict]


# Engineering screening thresholds.  They identify observations that deserve
# review; they are not sensor specifications or metrological acceptance limits.
CONTRADICTION_DELTA = {
    "air_temperature_c": 2.0,
    "relative_humidity_pct": 15.0,
    "solar_w_m2": 300.0,
    "wind_speed_m_s": 3.0,
    "pressure_hpa": 15.0,
}


def select_inputs(readings: list[Observation], event_time: str, zone_id: str) -> FusionResult:
    event_dt = iso_datetime(event_time)
    selected: dict[str, Observation] = {}
    rejected: list[dict] = []
    warnings: list[str] = []
    contradictions: list[dict] = []
    valid: list[Observation] = []

    for obs in readings:
        reason = None
        if obs.kind == "neighbor" and obs.zone_id != zone_id:
            reason = "El clip vecino debe indicar la MISMA zona validada."
        if obs.timestamp and reason is None:
            delta = abs((event_dt - iso_datetime(obs.timestamp)).total_seconds())
            max_age = MAX_AGE_S[obs.kind]
            if max_age is not None and delta > max_age:
                reason = f"Lectura desfasada ({delta:.0f} s; máximo {max_age} s)."
        if reason:
            rejected.append({"observation": obs.as_dict(), "reason": reason})
        else:
            valid.append(obs)

    # Nunca escoger una lectura vencida; preferir medición propia antes que
    # pronóstico, inferencia, vecino o suposición.
    for obs in sorted(valid, key=lambda o: PRIORITY[o.kind]):
        if obs.parameter not in selected:
            selected[obs.parameter] = obs

    by_parameter: dict[str, list[Observation]] = {}
    for obs in valid:
        by_parameter.setdefault(obs.parameter, []).append(obs)
    for parameter, candidates in by_parameter.items():
        tolerance = CONTRADICTION_DELTA.get(parameter)
        if tolerance is None or len(candidates) < 2:
            continue
        low = min(candidates, key=lambda item: item.value)
        high = max(candidates, key=lambda item: item.value)
        delta = high.value - low.value
        if delta > tolerance:
            contradictions.append({
                "parameter": parameter,
                "spread": round(delta, 4),
                "screening_threshold": tolerance,
                "lowest": {"value": low.value, "source": low.source, "kind": low.kind},
                "highest": {"value": high.value, "source": high.source, "kind": high.kind},
                "meaning": "Fuentes temporalmente válidas discrepan; requiere revisión, no prueba cuál es correcta.",
            })

    if any(x.kind == "assumed" for x in selected.values()):
        warnings.append("Se utilizaron hipótesis de escenario; no representan mediciones reales.")
    if any(x.kind == "neighbor" for x in selected.values()):
        warnings.append("Se usaron datos de otra persona/dispositivo: la coincidencia de zona no prueba igualdad ambiental.")
    if contradictions:
        warnings.append(f"{len(contradictions)} variable(s) presentan fuentes contradictorias; revisar procedencia y calibración.")
    for key in REQUIRED:
        if key not in selected:
            warnings.append(f"Sin {key}: no se pueden calcular los indicadores térmicos básicos.")
    return FusionResult(chosen=selected, rejected=rejected, warnings=warnings,
                        contradictions=contradictions)
