"""Diagnóstico de ingeniería de telemetría; no determina seguridad ocupacional.

Los umbrales de cambios abruptos y de valores repetidos son reglas de
*diagnóstico exploratorio*. No son especificaciones del HTU21D ni límites de
exposición. El estado se reinicia al reiniciar el proceso y se reconstruye desde
un historial pequeño en FleetService.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .schema import iso_datetime


@dataclass
class _DeviceState:
    timestamp: datetime | None = None
    temperature: float | None = None
    humidity: float | None = None
    first_equal_at: datetime | None = None
    consecutive_equal: int = 0


@dataclass
class EngineeringTelemetryMonitor:
    """Detector ligero de anomalías; conserva estado por device_id.

    No publica mensajes como 'seguro', 'calibrado' ni 'conectado'. No opera
    alertas de seguridad. Los límites son heurísticos y visibles en el reporte.
    """

    _state: dict[str, _DeviceState] = field(default_factory=dict)
    abrupt_temp_c: float = 5.0
    abrupt_humidity_pp: float = 25.0
    jump_window_seconds: float = 120.0
    flatline_consecutive: int = 6
    flatline_seconds: float = 60.0

    def inspect(self, event: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        device_id = event['device_id']
        when = iso_datetime(event['timestamp'])
        values = result.get('inputs_selected', {})
        transport = event.get('transport_metadata') or {}
        simulated = bool(transport.get('simulated', False))
        selected = {k: v['value'] for k, v in values.items()}
        t = selected.get('air_temperature_c')
        rh = selected.get('relative_humidity_pct')
        battery = selected.get('battery_level_pct')
        previous = self._state.setdefault(device_id, _DeviceState())
        flags: list[dict[str, str]] = []

        def flag(code: str, detail: str):
            flags.append({'code': code, 'detail': detail})

        if simulated:
            flag('SIMULATED', 'Datos de laboratorio virtual; ninguna medición procede del clip físico.')
        if t is None or rh is None:
            flag('MISSING_SENSOR_PAIR', 'No hay una pareja de T/RH seleccionada con calidad temporal suficiente.')
        if simulated and any(v.get('kind') == 'measured' for v in values.values()):
            flag('SIMULATED_MISLABELED', 'Un dato simulado fue marcado como medición física.')
        if battery is not None and battery <= 15:
            flag('LOW_BATTERY', 'Batería estimada ≤15%; planificar recarga y vigilar pérdida de comunicación.')
        rejected = result.get('inputs_rejected', [])
        if rejected:
            flag('REJECTED_OBSERVATIONS', f'{len(rejected)} observaciones descartadas por los filtros de fusión.')
        contradictions = result.get('input_contradictions', [])
        if contradictions:
            names = ', '.join(x.get('parameter','?') for x in contradictions)
            flag('CONTRADICTORY_SOURCES', f'Fuentes discrepantes para: {names}.')
        environmental = result.get('environmental_estimator_v18', {})
        if environmental.get('status') == 'missing_inputs':
            missing = ', '.join(environmental.get('missing', []))
            flag('MISSING_WBGT_INPUTS', f'No hay WBGT estimado: faltan {missing}.')
        elif environmental.get('status') == 'not_applicable':
            flag('OUTDOOR_MODEL_NOT_APPLICABLE', 'El modelo meteorológico exterior no se aplica en este entorno.')
        elif environmental.get('status') == 'model_error':
            flag('MODEL_ERROR', 'Revisar entradas o parametrización del estimador.')
        elif environmental.get('status') == 'computed':
            quality = environmental.get('input_quality', {}).get('category')
            if quality in ('scenario_only', 'unverified_inference'):
                flag('ESTIMATE_UNVERIFIED_INPUTS', 'WBGT estimado solo para exploración; fuentes no verificadas.')
            elif quality in ('mixed_local_and_external', 'external_only'):
                flag('REGIONAL_WEATHER', 'Parte de las entradas no representan mediciones de la zona del trabajador.')

        if previous.timestamp is not None:
            seconds = (when - previous.timestamp).total_seconds()
            if seconds <= 0:
                flag('NON_MONOTONIC_TIMESTAMP', 'Marca horaria repetida o anterior; no se actualiza histórico del monitor.')
            elif t is not None and rh is not None:
                if seconds <= self.jump_window_seconds:
                    if previous.temperature is not None and abs(t - previous.temperature) > self.abrupt_temp_c:
                        flag('ABRUPT_T_CHANGE', 'Cambio térmico rápido; investigar movimiento, radiación o lectura anómala.')
                    if previous.humidity is not None and abs(rh - previous.humidity) > self.abrupt_humidity_pp:
                        flag('ABRUPT_RH_CHANGE', 'Cambio de humedad rápido; investigar entorno o lectura anómala.')
                # Exactitud de dos decimales: detecta constancia, no necesariamente avería.
                same = (t == previous.temperature and rh == previous.humidity)
                if same:
                    previous.consecutive_equal += 1
                    if previous.first_equal_at is None:
                        previous.first_equal_at = previous.timestamp
                    duration = (when - previous.first_equal_at).total_seconds()
                    if previous.consecutive_equal >= self.flatline_consecutive and duration >= self.flatline_seconds:
                        flag('POSSIBLE_FLATLINE', 'T/RH idénticas durante varios mensajes; ambiente estable o sensor sin actualizar.')
                else:
                    previous.consecutive_equal = 1
                    previous.first_equal_at = when
        else:
            seconds = None

        if previous.timestamp is None or (when > previous.timestamp):
            previous.timestamp = when
            previous.temperature = t
            previous.humidity = rh
            if previous.consecutive_equal == 0 and t is not None and rh is not None:
                previous.consecutive_equal = 1
                previous.first_equal_at = when

        review_codes = {'SIMULATED_MISLABELED', 'ABRUPT_T_CHANGE', 'ABRUPT_RH_CHANGE',
                        'POSSIBLE_FLATLINE', 'NON_MONOTONIC_TIMESTAMP', 'MODEL_ERROR'}
        review_codes.update({'CONTRADICTORY_SOURCES','LOW_BATTERY'})
        incomplete_codes = {'MISSING_SENSOR_PAIR', 'MISSING_WBGT_INPUTS', 'OUTDOOR_MODEL_NOT_APPLICABLE'}
        codes = {x['code'] for x in flags}
        status = ('review_data' if codes & review_codes else
                  'incomplete_for_outdoor_wbgt' if codes & incomplete_codes else
                  'simulation_only' if simulated else 'research_only_unvalidated')
        return {
            'status': status,
            'flags': flags,
            'flag_codes': [x['code'] for x in flags],
            'temperature_c': t, 'relative_humidity_pct': rh,
            'wbgt_estimate_available': environmental.get('status') == 'computed',
            'source_summary': {k: {'kind': v['kind'], 'source': v['source']} for k, v in values.items()},
            'heuristic_thresholds': {
                'abrupt_temp_c': self.abrupt_temp_c,
                'abrupt_humidity_percentage_points': self.abrupt_humidity_pp,
                'window_seconds': self.jump_window_seconds,
                'flatline_samples': self.flatline_consecutive,
                'flatline_seconds': self.flatline_seconds,
            },
            'validated_sensor': False,
            'validated_occupational_wbgt': False,
            'occupational_alerts_enabled': False,
            'meaning': 'Diagnóstico de calidad de datos, NO evaluación de riesgo térmico o seguridad de trabajadores.',
        }
