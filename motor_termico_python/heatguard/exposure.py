"""Acumulación de tiempo sobre un umbral EXPLORATORIO de Heat Index.

No es el cálculo normativo de exposición TGBH ni confirma que haya seguridad.
Se trata de un indicador temporal con posible cobertura incompleta.
"""
from __future__ import annotations
from dataclasses import dataclass
from .schema import iso_datetime


@dataclass
class ExposureState:
    last_timestamp: str | None = None
    last_hi_c: float | None = None
    minutes_above_hi: float = 0.0
    covered_minutes: float = 0.0
    missing_minutes: float = 0.0
    duplicates_or_reverse: int = 0

    def update(self, timestamp: str, heat_index_c: float | None,
               *, threshold_c: float = 32.0, max_gap_s: float = 180.0) -> dict:
        """Integración por retención de muestra previa, sin rellenar grandes huecos."""
        iso_datetime(timestamp)
        if self.last_timestamp is not None:
            dt = (iso_datetime(timestamp) - iso_datetime(self.last_timestamp)).total_seconds()
            if dt <= 0:
                self.duplicates_or_reverse += 1
                return self.snapshot(threshold_c)
            if dt > max_gap_s or self.last_hi_c is None:
                self.missing_minutes += dt / 60
            else:
                self.covered_minutes += dt / 60
                if self.last_hi_c >= threshold_c:
                    self.minutes_above_hi += dt / 60
        self.last_timestamp = timestamp
        self.last_hi_c = heat_index_c
        return self.snapshot(threshold_c)

    def snapshot(self, threshold_c: float = 32.0) -> dict:
        return {
            'type': 'heat_index_exposure_research_only', 'threshold_c': threshold_c,
            'minutes_above_threshold': round(self.minutes_above_hi, 3),
            'covered_minutes': round(self.covered_minutes, 3),
            'missing_minutes': round(self.missing_minutes, 3),
            'out_of_order_samples': self.duplicates_or_reverse,
            'not_normative_wbgt': True, 'safety_alert_enabled': False,
            'interpretation': 'Tiempo experimental sobre umbral HI configurado; no sustituye exposición TGBH.',
        }
