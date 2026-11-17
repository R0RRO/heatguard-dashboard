"""Orquestador offline-first: fuentes, estimación, red de clips, exposición, historiales.

La telemetría y los cálculos quedan disponibles sin ningún ESP32 conectado.
"""
from __future__ import annotations
from collections import defaultdict
import os
from datetime import datetime, timezone
from threading import RLock
from .exposure import ExposureState
from .exposure_v22 import DeviceExposureV22
from .radiation_v22 import prepare_radiation
from .context_estimation import relative_airflow_scenario
from .fusion import select_inputs
from .neighbors import neighbor_candidates
from .occupational import research_assessment
from .pipeline import evaluate
from .repository import EventRepository
from .scenarios import SiteScenario, apply_explicit_scenario
from .schema import iso_datetime, read_event, check_sensitive_ingestion
from .weather import WeatherProvider
from .telemetry_quality_v19 import EngineeringTelemetryMonitor
from .review_engine import ExperimentalReviewEngine


DEVICE_EVENT_TYPES = {
    'hydration_self_report', 'button_short_press', 'button_counter_reset'
}


def _tracking_subject(event: dict) -> tuple[str, str]:
    worker = event.get('context',{}).get('worker_id')
    if isinstance(worker,str) and worker.strip():
        return ('worker_pseudonym',worker.strip())
    return ('device',event['device_id'])


class FleetService:
    def __init__(self, db_path='data/heatguard_v04.sqlite', *, scenario: SiteScenario | None = None,
                 weather_provider: WeatherProvider | None = None):
        self.repository = EventRepository(db_path)
        self.scenario = scenario
        self.weather_provider = weather_provider
        self._lock = RLock()
        self._quality = EngineeringTelemetryMonitor()
        self._latest: dict[str, dict] = {}
        self._exposure: dict[str, ExposureState] = defaultdict(ExposureState)
        self._exposure_v22: dict[str, DeviceExposureV22] = defaultdict(DeviceExposureV22)
        self._review = ExperimentalReviewEngine()
        model_path = os.environ.get("HG_ML_MODEL_PATH")
        self._residual_model = None
        if model_path:
            from .ml import ResidualModel
            model_sha256 = os.environ.get('HG_ML_MODEL_SHA256')
            if not model_sha256:
                raise RuntimeError('HG_ML_MODEL_SHA256 es obligatorio al configurar HG_ML_MODEL_PATH')
            self._residual_model = ResidualModel(model_path, expected_sha256=model_sha256)
        self._restore()

    def _restore(self):
        # Rebuild the complete persisted shift horizon, including pseudonymous
        # workers that changed clips.  Event time keeps simulations reproducible.
        for item in self.repository.records_for_restore(horizon_hours=24):
            event, result = item['event'], item['result']
            device_id = event['device_id']
            self._quality.inspect(event, result)
            self._latest[device_id] = event
            metric = result.get('metrics', {}).get('heat_index_c', {})
            self._exposure[device_id].update(event['timestamp'], metric.get('value_c'))
            subject = _tracking_subject(event)
            context = event.get('context', {})
            self._exposure_v22[subject].update(
                event['timestamp'], result.get('environmental_estimator_v18',{}),
                result.get('decision_support_v22',{}),
                activity_class=context.get('activity_class','unknown'),
                work_state=context.get('work_state') if 'work_state' in context else None,
                zone_id=context.get('zone_id','unknown'),
                shift_duration_hours=context.get('shift_duration_hours'))
            self._review.restore(f'{subject[0]}:{subject[1]}', event['timestamp'],
                                 result.get('review_state_v23', {}))

    def ingest(self, event: dict, *, use_scenario: bool = False, use_neighbors: bool = False,
               use_online_weather: bool = False) -> dict:
        """Los 3 interruptores opcionales son explícitos; el modo normal no inventa datos."""
        with self._lock:
            _, _, _, incoming_context, incoming_readings = read_event(event)
            check_sensitive_ingestion(incoming_context, incoming_readings)
            raw = dict(event)
            # Los datos meteorológicos reales/fuentes externas tienen prioridad;
            # las hipótesis solo completan lo que no llegó con el evento.
            if use_online_weather:
                if self.weather_provider is None:
                    return {'error': 'weather_unavailable', 'detail': 'Proveedor no configurado'}
                raw, ingestion_warnings = self.weather_provider.enrich(raw)
            else:
                ingestion_warnings = []
            raw, radiation_info = prepare_radiation(raw)
            enriched = apply_explicit_scenario(raw, self.scenario, enabled=use_scenario)
            if use_neighbors:
                enriched.setdefault('observations', []).extend(neighbor_candidates(enriched, self._latest))
            result = evaluate(enriched)
            result["radiative_context_v22"] = radiation_info
            if ingestion_warnings:
                result['ingestion_warnings'] = ingestion_warnings
            result["relative_airflow_context"] = relative_airflow_scenario(result["inputs_selected"])
            # La corrección ML exige un modelo entrenado FUERA de este servicio con referencia.
            wbgt = result.get("wbgt_outdoor_model", {})
            if self._residual_model is not None and wbgt.get("status") == "computed":
                model_inputs = {k: v["value"] for k, v in result["inputs_selected"].items()}
                model_inputs["wbgt_physical_c"] = wbgt["value_c"]
                result["wbgt_hybrid_research"] = self._residual_model.predict(model_inputs)
            else:
                result["wbgt_hybrid_research"] = {"status": "model_not_loaded_or_no_physical_baseline",
                                                   "normative_measurement": False}
            # Si es un reenvío idéntico no se debe acumular exposición otra vez.
            if self.repository.exists(enriched):
                return {'accepted': False, 'duplicate': True, 'device_id': enriched['device_id'],
                        'note': 'Evento ya registrado; no se cuenta exposición dos veces'}
            device_id = enriched['device_id']
            result['engineering_quality_v19'] = self._quality.inspect(enriched, result)
            hi = result.get('metrics', {}).get('heat_index_c', {}).get('value_c')
            previous_state = self._exposure[device_id]
            exposure = previous_state.update(enriched['timestamp'], hi)
            result['experimental_exposure'] = exposure
            band = result.get('decision_support_v22', {})
            tracking_subject = _tracking_subject(enriched)
            result['exposure_timeline_v22'] = self._exposure_v22[tracking_subject].update(
                enriched['timestamp'], result.get('environmental_estimator_v18',{}), band,
                activity_class=enriched['context'].get('activity_class','unknown'),
                work_state=(enriched['context'].get('work_state')
                            if 'work_state' in enriched['context'] else None),
                zone_id=enriched['context'].get('zone_id','unknown'),
                shift_duration_hours=enriched['context'].get('shift_duration_hours'))
            result['exposure_timeline_v22']['subject_type'] = tracking_subject[0]
            review_cfg = enriched['context'].get('research_review', {})
            if isinstance(review_cfg, dict) and 'duration_review_min' in review_cfg:
                duration = review_cfg['duration_review_min']
                if isinstance(duration,bool) or not isinstance(duration,(int,float)) or not 0 < duration <= 480:
                    raise ValueError('context.research_review.duration_review_min debe estar en (0,480]')
                band['duration_review_reached'] = bool(
                    result['exposure_timeline_v22']['minutes_possible_ge_research_threshold'] >= duration)
                band['duration_condition_research_only'] = True
            result['review_state_v23'] = self._review.update(
                f'{tracking_subject[0]}:{tracking_subject[1]}', enriched['timestamp'], band,
                result['exposure_timeline_v22'], result['engineering_quality_v19'],
                contradictions=result.get('input_contradictions', []))
            result['occupational_research'] = research_assessment(result, exposure, enriched['context'])
            result['provenance_summary'] = {
                'all_inputs': [
                    {'parameter': k, 'kind': v['kind'], 'source': v['source']}
                    for k, v in result['inputs_selected'].items()
                ],
                'scenario_enabled': use_scenario,
                'neighbors_enabled': use_neighbors,
                'external_weather_enabled': use_online_weather,
                'simulated': bool(enriched.get('transport_metadata', {}).get('simulated')),
            }
            stored = self.repository.save(enriched, result)
            if not stored:
                return {'accepted': False, 'duplicate': True, 'device_id': device_id}
            current = self._latest.get(device_id)
            if current is None or iso_datetime(enriched['timestamp']) >= iso_datetime(current['timestamp']):
                self._latest[device_id] = enriched
            return {'accepted': True, 'duplicate': False, 'device_id': device_id, 'result': result}

    def ingest_device_event(self, event: dict) -> dict:
        """Persiste eventos discretos del clip sin convertirlos en mediciones."""
        if not isinstance(event, dict):
            raise ValueError('El evento del dispositivo debe ser un objeto')
        device_id = str(event.get('device_id', '')).strip()
        event_id = str(event.get('event_id', '')).strip()
        event_type = str(event.get('event_type', '')).strip()
        source = str(event.get('source', '')).strip()
        if not device_id or not event_id or not source:
            raise ValueError('device_id, event_id y source son obligatorios')
        if len(device_id) > 128 or len(event_id) > 256 or len(source) > 128:
            raise ValueError('Identificador de evento demasiado extenso')
        iso_datetime(str(event.get('timestamp', '')))
        if event_type not in DEVICE_EVENT_TYPES:
            raise ValueError(f'event_type no reconocido: {event_type!r}')
        metadata = event.get('metadata', {})
        if not isinstance(metadata, dict):
            raise ValueError('metadata debe ser objeto')
        physiological = event.get('physiological_measurement')
        if physiological is not False:
            raise ValueError('physiological_measurement debe ser false para eventos de botón')
        self_reported = event.get('self_reported')
        if event_type == 'hydration_self_report' and self_reported is not True:
            raise ValueError('hydration_self_report debe declararse self_reported=true')
        stored = self.repository.save_device_event(event)
        return {
            'accepted': stored, 'duplicate': not stored, 'device_id': device_id,
            'event_id': event_id, 'event_type': event_type,
            'physiological_measurement': False,
            'note': ('Evento autodeclarado persistido; no mide hidratación corporal.'
                     if event_type == 'hydration_self_report'
                     else 'Evento discreto del dispositivo persistido.'),
        }

    def latest(self, device_id=None) -> list[dict] | dict | None:
        with self._lock:
            if device_id is not None:
                rows = self.repository.latest(device_id, 1)
                return rows[0] if rows else None
            return [self.repository.latest(dev, 1)[0] for dev in self.repository.device_ids()]

    def fleet_summary(self) -> dict:
        rows = self.latest()
        return {
            'device_count': len(rows),
            'stored_events': self.repository.count(),
            'devices': [self._summary(row) for row in rows],
            'safety_alerts_enabled': False,
            'message': 'Datos de desarrollo. No usar ausencia de alertas como confirmación de seguridad.',
        }

    @staticmethod
    def _summary(item: dict) -> dict:
        event, result = item['event'], item['result']
        return {'device_id': event['device_id'], 'worker_id': event['context'].get('worker_id'),
                'zone_id': result['zone_id'], 'timestamp': event['timestamp'],
                'simulated': result.get('provenance_summary', {}).get('simulated', False),
                'heat_index_c': result.get('metrics', {}).get('heat_index_c', {}).get('value_c'),
                'wbgt_model': result.get('wbgt_outdoor_model', {}),
                'environmental_estimator_v18': result.get('environmental_estimator_v18', {}),
                'experimental_exposure': result.get('experimental_exposure', {}),
                'exposure_timeline_v22': result.get('exposure_timeline_v22', {}),
                'decision_support_v22': result.get('decision_support_v22', {}),
                'review_state_v23': result.get('review_state_v23', {}),
                'radiative_context_v22': result.get('radiative_context_v22', {}),
                'battery_pct': result.get('inputs_selected',{}).get('battery_level_pct',{}).get('value'),
                'steps_since_boot': result.get('inputs_selected',{}).get('steps_since_boot',{}).get('value'),
                'acceleration_magnitude_g': result.get('inputs_selected',{}).get('acceleration_magnitude_g',{}).get('value'),
                'hydration_self_report_count': result.get('inputs_selected',{}).get('hydration_self_report_count',{}).get('value'),
                'occupational_research': result.get('occupational_research', {}),
                'inputs': result.get('inputs_selected', {}),
                'engineering_quality_v19': result.get('engineering_quality_v19', {}),
                'risk_is_validated': False}

    def zones(self) -> list[dict]:
        grouped: dict[str, list[dict]] = defaultdict(list)
        for row in self.latest():
            grouped[row['result']['zone_id']].append(self._summary(row))
        out = []
        for zone_id, devices in sorted(grouped.items()):
            values = [d['inputs'].get('air_temperature_c', {}).get('value') for d in devices]
            valid = [v for v in values if v is not None]
            out.append({'zone_id': zone_id, 'devices': len(devices),
                        'temperature_mean_c': round(sum(valid) / len(valid), 2) if valid else None,
                        'interpretation': 'Promedio descriptivo, NO intercambiable con medición de cada puesto'})
        return out
