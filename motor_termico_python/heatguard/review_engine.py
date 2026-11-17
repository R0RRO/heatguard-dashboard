"""Stateful, research-only review workflow with persistence and hysteresis.

This engine creates review events for a human supervisor.  It deliberately
does not control the clip LED/vibration or authorize work/rest decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .schema import iso_datetime


@dataclass
class ReviewMemory:
    state: str = "data_insufficient"
    last_timestamp: datetime | None = None
    last_review_event_at: datetime | None = None


class ExperimentalReviewEngine:
    def __init__(self):
        self._states: dict[str, ReviewMemory] = {}

    def restore(self, subject_id: str, timestamp: str, output: dict) -> None:
        if not isinstance(output, dict):
            return
        state = output.get("state")
        if not isinstance(state, str):
            return
        memory = self._states.setdefault(subject_id, ReviewMemory())
        when = iso_datetime(timestamp)
        if memory.last_timestamp is None or when >= memory.last_timestamp:
            memory.state = state
            memory.last_timestamp = when
            emitted = output.get("review_event_at")
            if isinstance(emitted, str):
                memory.last_review_event_at = iso_datetime(emitted)

    def update(self, subject_id: str, timestamp: str, band: dict, exposure: dict,
               quality: dict, *, contradictions: list[dict] | None = None) -> dict:
        now = iso_datetime(timestamp)
        memory = self._states.setdefault(subject_id, ReviewMemory())
        if memory.last_timestamp is not None and now < memory.last_timestamp:
            return {
                "state": memory.state,
                "reason": "Evento tardío conservado sin rebobinar el estado actual de revisión.",
                "state_changed": False, "review_event_emitted": False,
                "review_event_at": (memory.last_review_event_at.isoformat()
                                    if memory.last_review_event_at else None),
                "repeat_suppressed": True, "ignored_out_of_order": True,
                "research_only": True,
                "human_review_required": memory.state in {
                    "attention", "priority_review", "data_insufficient", "data_quality_review"
                },
                "automatic_actuator_command": False, "safety_alert_enabled": False,
                "absence_is_not_safety_clearance": True,
            }
        cfg_ready = band.get("status") != "not_configured"
        severe_quality = {"MISSING_SENSOR_PAIR", "MISSING_WBGT_INPUTS", "MODEL_ERROR",
                          "NON_MONOTONIC_TIMESTAMP", "SIMULATED_MISLABELED"}
        quality_codes = set(quality.get("flag_codes", []))
        coverage = float(exposure.get("coverage_of_window_fraction") or 0)
        minimum_coverage = float(band.get("minimum_coverage_fraction", 0.5))

        reason = ""
        candidate = "sufficient_no_review_criterion"
        if band.get("status") in {"missing_estimate"} or quality_codes & severe_quality:
            candidate = "data_insufficient"
            reason = "Estimación o telemetría insuficiente/inconsistente."
        elif contradictions:
            candidate = "data_quality_review"
            reason = "Fuentes ambientales contradictorias."
        elif not cfg_ready:
            candidate = "sufficient_no_review_rule"
            reason = "Hay datos, pero no existe una regla experimental configurada."
        elif coverage < minimum_coverage and exposure.get("observed_span_minutes", 0) >= 15:
            candidate = "data_insufficient"
            reason = "Cobertura temporal inferior a la requerida por la regla."
        elif band.get("attention") == "priority_review":
            candidate = "priority_review"
            reason = "Toda la banda asumida supera el corte de investigación."
        elif band.get("attention") == "review":
            candidate = "attention"
            reason = "La banda asumida intersecta el corte de investigación."

        duration_required = float(band.get("duration_review_min", 0))
        duration_observed = 0.0
        if candidate == "priority_review":
            duration_observed = float(exposure.get("minutes_entire_band_ge_research_threshold", 0))
        elif candidate == "attention":
            duration_observed = float(exposure.get("minutes_possible_ge_research_threshold", 0))
        if candidate in {"attention", "priority_review"} and duration_observed < duration_required:
            candidate = "monitoring_persistence"
            reason = "Condición detectada; aún no cumple la persistencia configurada."

        # Do not clear an active human-review state for tiny oscillations around
        # the research threshold.  This is workflow hysteresis, not a safety rule.
        threshold = band.get("threshold_c")
        upper = band.get("band_upper_c")
        hysteresis = float(band.get("hysteresis_c", 0.5))
        if (memory.state in {"attention", "priority_review"}
                and candidate == "sufficient_no_review_criterion"
                and threshold is not None and upper is not None
                and float(upper) >= float(threshold) - hysteresis):
            candidate = "attention"
            reason = "Estado conservado por histéresis de la regla experimental."

        review_states = {"attention", "priority_review", "data_insufficient", "data_quality_review"}
        repeat_minutes = float(band.get("repeat_suppression_min", 30))
        changed = candidate != memory.state
        due = (memory.last_review_event_at is None or
               now - memory.last_review_event_at >= timedelta(minutes=repeat_minutes))
        emit = candidate in review_states and (changed or due)
        if emit:
            memory.last_review_event_at = now
        memory.state = candidate
        memory.last_timestamp = now
        return {
            "state": candidate,
            "reason": reason,
            "state_changed": changed,
            "review_event_emitted": emit,
            "review_event_at": now.isoformat() if emit else (
                memory.last_review_event_at.isoformat() if memory.last_review_event_at else None
            ),
            "repeat_suppressed": candidate in review_states and not emit,
            "duration_required_minutes": duration_required,
            "duration_observed_minutes": round(duration_observed, 3),
            "minimum_coverage_fraction": minimum_coverage,
            "coverage_fraction": coverage,
            "hysteresis_c": hysteresis,
            "research_only": True,
            "human_review_required": candidate in review_states,
            "automatic_actuator_command": False,
            "safety_alert_enabled": False,
            "absence_is_not_safety_clearance": True,
        }
