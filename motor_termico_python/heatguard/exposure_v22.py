"""Exposición por tiempo de evento, con trabajo y descanso independientes.

Los huecos mayores a ``max_gap_seconds`` quedan SIN DATOS. Las muestras se
mantienen ordenadas para que un reenvío tardío no rebobine ni corrompa el
estado actual. ``work_state`` describe trabajo/descanso; ``activity_class``
describe intensidad y nunca reemplaza al primero cuando está declarado.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import timedelta, datetime
from .schema import iso_datetime


ACTIVITY_CLASSES = {'resting', 'light', 'moderate', 'heavy', 'very_heavy', 'unknown'}
WORK_STATES = {'working', 'resting', 'break', 'off_shift', 'unknown'}


@dataclass
class ExposureSample:
    timestamp: datetime
    wbgt_c: float | None
    low_c: float | None
    high_c: float | None
    threshold_c: float | None
    activity_class: str
    work_state: str
    zone_id: str
    condition: str


@dataclass
class Interval:
    start: datetime
    end: datetime
    wbgt_c: float | None
    low_c: float | None
    high_c: float | None
    threshold_c: float | None
    activity: str
    work_state: str
    covered: bool
    zone_id: str = 'unknown'
    condition: str = 'unknown'


@dataclass
class DeviceExposureV22:
    last_timestamp: datetime | None = None
    last_wbgt_c: float | None = None
    last_low_c: float | None = None
    last_high_c: float | None = None
    last_threshold_c: float | None = None
    last_activity: str = 'unknown'  # alias compatible: activity_class
    last_work_state: str = 'unknown'
    last_zone_id: str = 'unknown'
    last_condition: str = 'unknown'
    samples: list[ExposureSample] = field(default_factory=list)
    intervals: list[Interval] = field(default_factory=list)
    duplicates_or_reverse: int = 0
    max_gap_seconds: float = 300.0
    history_horizon_hours: float = 8.0

    @staticmethod
    def _condition(wbgt: dict, band: dict) -> str:
        if wbgt.get('status') != 'computed':
            return 'unknown'
        threshold = band.get('threshold_c')
        if threshold is None:
            return 'estimated_without_review_threshold'
        if band.get('band_lower_c') is not None and band['band_lower_c'] >= threshold:
            return 'entire_band_above_research_threshold'
        if band.get('band_upper_c') is not None and band['band_upper_c'] >= threshold:
            return 'band_intersects_research_threshold'
        return 'below_research_threshold'

    @staticmethod
    def _work_state(value: str | None, activity_class: str) -> str:
        if value is None:
            # Compatibilidad con registros v0.22/v0.30 que no tenían el campo.
            if activity_class == 'resting':
                return 'resting'
            if activity_class in {'light', 'moderate', 'heavy', 'very_heavy'}:
                return 'working'
            return 'unknown'
        return value if value in WORK_STATES else 'unknown'

    def update(self, timestamp: str, wbgt: dict, band: dict, *,
               activity: str | None = None, activity_class: str | None = None,
               work_state: str | None = None, zone_id: str = 'unknown',
               shift_duration_hours: float | None = None) -> dict:
        now = iso_datetime(timestamp)
        if shift_duration_hours is not None:
            value = float(shift_duration_hours)
            if not 1 <= value <= 24:
                raise ValueError('shift_duration_hours debe estar entre 1 y 24')
            self.history_horizon_hours = value
        selected_activity = activity_class if activity_class is not None else activity
        selected_activity = (selected_activity if selected_activity in ACTIVITY_CLASSES else 'unknown')
        selected_work_state = self._work_state(work_state, selected_activity)
        if any(sample.timestamp == now for sample in self.samples):
            self.duplicates_or_reverse += 1
            return self.snapshot(self.last_timestamp or now)
        if self.last_timestamp is not None and now < self.last_timestamp:
            self.duplicates_or_reverse += 1
        sample = ExposureSample(
            timestamp=now,
            wbgt_c=wbgt.get('value_c') if wbgt.get('status') == 'computed' else None,
            low_c=band.get('band_lower_c'), high_c=band.get('band_upper_c'),
            threshold_c=band.get('threshold_c'), activity_class=selected_activity,
            work_state=selected_work_state, zone_id=str(zone_id or 'unknown'),
            condition=self._condition(wbgt, band),
        )
        self.samples.append(sample)
        self.samples.sort(key=lambda item: item.timestamp)
        latest = self.samples[-1].timestamp
        cutoff = latest - timedelta(hours=self.history_horizon_hours)
        # Mantener una muestra anterior permite formar el intervalo que cruza el corte.
        before = [s for s in self.samples if s.timestamp < cutoff]
        after = [s for s in self.samples if s.timestamp >= cutoff]
        self.samples = ([before[-1]] if before else []) + after
        self._rebuild()
        return self.snapshot(self.last_timestamp)

    def _rebuild(self) -> None:
        self.intervals = []
        for previous, current in zip(self.samples, self.samples[1:]):
            seconds = (current.timestamp - previous.timestamp).total_seconds()
            covered = 0 < seconds <= self.max_gap_seconds and previous.wbgt_c is not None
            self.intervals.append(Interval(
                previous.timestamp, current.timestamp,
                previous.wbgt_c if covered else None,
                previous.low_c if covered else None,
                previous.high_c if covered else None,
                previous.threshold_c if covered else None,
                previous.activity_class, previous.work_state, covered,
                previous.zone_id, previous.condition,
            ))
        if not self.samples:
            return
        last = self.samples[-1]
        self.last_timestamp = last.timestamp
        self.last_wbgt_c = last.wbgt_c
        self.last_low_c = last.low_c
        self.last_high_c = last.high_c
        self.last_threshold_c = last.threshold_c
        self.last_activity = last.activity_class
        self.last_work_state = last.work_state
        self.last_zone_id = last.zone_id
        self.last_condition = last.condition

    def snapshot(self, now: datetime | None = None) -> dict:
        now = now or self.last_timestamp
        if now is None:
            return {'status': 'no_samples', 'safety_alert_enabled': False}
        result = self._window_snapshot(now, minutes=60)
        result['rolling_windows'] = {
            '15m': self._window_snapshot(now, minutes=15, include_shift=False),
            '30m': self._window_snapshot(now, minutes=30, include_shift=False),
            '60m': {k: v for k, v in result.items()
                    if k not in ('rolling_windows', 'rolling_shift', 'rolling_8h')},
        }
        return result

    def _window_snapshot(self, now: datetime, minutes: int, *, include_shift: bool = True) -> dict:
        cutoff = now - timedelta(minutes=minutes)
        start_span = None
        covered = missing = weighted = 0.0
        central = possible = certain = 0.0
        work = rest = off_shift = 0.0
        for interval in self.intervals:
            left = max(interval.start, cutoff); right = min(interval.end, now)
            if right <= left:
                continue
            if start_span is None or left < start_span:
                start_span = left
            mins = (right - left).total_seconds() / 60
            if not interval.covered:
                missing += mins
                continue
            covered += mins
            weighted += mins * float(interval.wbgt_c)
            if interval.threshold_c is not None:
                if interval.wbgt_c >= interval.threshold_c: central += mins
                if interval.high_c is not None and interval.high_c >= interval.threshold_c: possible += mins
                if interval.low_c is not None and interval.low_c >= interval.threshold_c: certain += mins
            if interval.work_state == 'working': work += mins
            elif interval.work_state in ('resting', 'break'): rest += mins
            elif interval.work_state == 'off_shift': off_shift += mins
        unknown_state = max(0.0, covered - work - rest - off_shift)
        window_span = (now - start_span).total_seconds() / 60 if start_span else 0.0
        result = {
            'status': 'tracked' if self.intervals else 'initial_sample',
            'window_minutes': minutes,
            'observed_span_minutes': round(window_span, 3),
            'covered_minutes': round(covered, 3),
            'missing_minutes': round(missing, 3),
            'coverage_of_window_fraction': round(covered / minutes, 4),
            'coverage_of_full_hour_fraction': round(covered / 60, 4) if minutes == 60 else None,
            'experimental_time_weighted_wbgt_c': round(weighted / covered, 3) if covered else None,
            'minutes_central_ge_research_threshold': round(central, 3),
            'minutes_possible_ge_research_threshold': round(possible, 3),
            'minutes_entire_band_ge_research_threshold': round(certain, 3),
            'minutes_declared_work': round(work, 3),
            'minutes_declared_rest': round(rest, 3),
            'minutes_declared_off_shift': round(off_shift, 3),
            'minutes_work_state_unknown': round(unknown_state, 3),
            'minutes_activity_unknown': round(unknown_state, 3),  # alias v0.22
            'out_of_order_samples': self.duplicates_or_reverse,
            'not_iso_7243_twa': True,
            'no_physiological_heat_dose_claim': True,
            'safety_alert_enabled': False,
            'exposure_evidence': 'estimated' if covered else 'unknown',
            'interpretation': ('Promedio temporal de ESTIMACIONES, con cobertura; no sustituye '
                               'TGBH instrumental ni estima temperatura corporal.'),
        }
        condition_minutes = self._trailing_minutes(now, 'condition', self.last_condition)
        zone_minutes = self._trailing_minutes(now, 'zone_id', self.last_zone_id)
        result.update({
            'current_condition': self.last_condition,
            'current_condition_duration_minutes': round(condition_minutes, 3),
            'current_zone_id': self.last_zone_id,
            'current_zone_duration_minutes': round(zone_minutes, 3),
            'current_work_state': self.last_work_state,
            'current_activity_class': self.last_activity,
            'current_recovery_duration_minutes': round(
                self._trailing_minutes(now, 'work_state', self.last_work_state), 3
            ) if self.last_work_state in ('resting', 'break') else 0.0,
        })
        if minutes == 60 and include_shift:
            shift_minutes = int(round(self.history_horizon_hours * 60))
            shift = self._window_snapshot(now, minutes=shift_minutes, include_shift=False)
            compact = {k: shift[k] for k in (
                'window_minutes', 'covered_minutes', 'missing_minutes', 'coverage_of_window_fraction',
                'minutes_central_ge_research_threshold', 'minutes_possible_ge_research_threshold',
                'minutes_entire_band_ge_research_threshold', 'minutes_declared_work',
                'minutes_declared_rest', 'minutes_declared_off_shift', 'minutes_work_state_unknown',
                'minutes_activity_unknown', 'experimental_time_weighted_wbgt_c')}
            compact['no_shift_normative_dose'] = True
            result['rolling_shift'] = compact
            if shift_minutes == 480:
                result['rolling_8h'] = dict(compact)
        return result

    def _trailing_minutes(self, now: datetime, field_name: str, expected: str) -> float:
        if expected == 'unknown' or not self.intervals:
            return 0.0
        total = 0.0
        cursor = now
        for interval in reversed(self.intervals):
            if interval.end > cursor:
                continue
            if (interval.end < cursor or not interval.covered or
                    getattr(interval, field_name) != expected):
                break
            total += (interval.end - interval.start).total_seconds() / 60
            cursor = interval.start
        return total
