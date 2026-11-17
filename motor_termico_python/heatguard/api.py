"""API de desarrollo HeatGuard v0.4.

Sin clave configurada SOLO debe ejecutarse en 127.0.0.1. Nunca publicar así.
Para Internet se necesitan autenticación real, TLS, políticas de acceso y auditoría.
"""
from __future__ import annotations
import os
import csv
import hmac
import io
from datetime import datetime, timezone
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from .fleet import FleetService
from .gateway import append_gateway_sources
from .live import live_store
from .pipeline import evaluate
from .schema import iso_datetime
from .scenarios import load_scenario
from .virtual_site import SITE_EXAMPLE, simulated_events
from .weather import WeatherProvider

app = FastAPI(title='HeatGuard Research Backend', version='0.31.0',
              description='Investigación: telemetría, fuentes, estimaciones, históricos y gemelo digital. Sin certificación ISO.')
allowed_origins = [o.strip() for o in os.environ.get('HG_ALLOWED_ORIGINS',
                   'http://localhost:5173,http://127.0.0.1:5173').split(',') if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins,
                   allow_credentials=False, allow_methods=['GET', 'POST'],
                   allow_headers=['Content-Type', 'X-API-Key'])
provider = WeatherProvider()
_site = load_scenario(os.environ.get('HG_SITE_SCENARIO_PATH'), SITE_EXAMPLE)
_fleet = FleetService(db_path=os.environ.get('HG_DB_PATH', 'data/heatguard_v04.sqlite'),
                      scenario=_site, weather_provider=provider)


def check_key(x_api_key: str | None = Header(default=None)):
    admin = os.environ.get('HG_ADMIN_API_KEY') or os.environ.get('HG_API_KEY')
    viewer = os.environ.get('HG_VIEWER_API_KEY')
    configured = [key for key in (admin, viewer) if key]
    if configured and not any(x_api_key is not None and hmac.compare_digest(x_api_key, key)
                              for key in configured):
        raise HTTPException(status_code=401, detail='X-API-Key requerida')
    return 'admin' if admin and x_api_key and hmac.compare_digest(x_api_key, admin) else 'viewer'


def check_admin_key(x_api_key: str | None = Header(default=None)):
    admin = os.environ.get('HG_ADMIN_API_KEY') or os.environ.get('HG_API_KEY')
    viewer = os.environ.get('HG_VIEWER_API_KEY')
    if admin:
        if x_api_key is None:
            raise HTTPException(status_code=401, detail='X-API-Key requerida')
        if not hmac.compare_digest(x_api_key, admin):
            raise HTTPException(status_code=403, detail='Se requiere clave de administración')
    elif viewer:
        raise HTTPException(status_code=503, detail='Configura HG_ADMIN_API_KEY para operaciones de escritura')
    return 'development_admin'


@app.get('/health')
def health():
    return {'status': 'ok', 'version': '0.31.0', 'mode': 'research_development',
            'hardware_required': False, 'safety_alerts_enabled': False}


@app.post('/v1/estimate', dependencies=[Depends(check_admin_key)])
def estimate(payload: dict):
    try:
        return evaluate(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post('/v1/estimate/with-weather', dependencies=[Depends(check_admin_key)])
def estimate_weather(payload: dict):
    try:
        enriched, warnings = provider.enrich(payload)
        result = evaluate(enriched)
        result['ingestion_warnings'] = warnings
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post('/v1/fleet/ingest', dependencies=[Depends(check_admin_key)])
def ingest(payload: dict, scenario: bool = False,
           neighbors: bool = False, online_weather: bool = False):
    try:
        result = _fleet.ingest(payload, use_scenario=scenario, use_neighbors=neighbors,
                               use_online_weather=online_weather)
        if result.get('error'):
            raise HTTPException(status_code=503, detail=result['detail'])
        if result.get('accepted'):
            live_store.put(payload, result['result'])
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# Compatibilidad con pasarela v0.3 y vista TelemetryLive.jsx
@app.post('/v1/live/ingest', dependencies=[Depends(check_admin_key)])
def ingest_live(payload: dict, scenario: bool = False):
    return ingest(payload, scenario=scenario)


@app.post('/v1/fleet/device-events', dependencies=[Depends(check_admin_key)])
def ingest_device_event(payload: dict):
    try:
        return _fleet.ingest_device_event(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get('/v1/live/devices', dependencies=[Depends(check_key)])
def live_devices():
    return {'devices': live_store.list(), 'risk_alerts_enabled': False,
            'note': 'Solo estado RAM desde que el servidor inició; histórico en /v1/fleet'}


@app.get('/v1/live/devices/{device_id}', dependencies=[Depends(check_key)])
def live_device(device_id: str):
    row = live_store.get(device_id)
    if row is None:
        raise HTTPException(status_code=404, detail='Clip sin datos en esta sesión')
    return row


@app.get('/v1/fleet', dependencies=[Depends(check_key)])
def fleet():
    return _fleet.fleet_summary()


@app.get('/v1/fleet/zones', dependencies=[Depends(check_key)])
def zones():
    return {'zones': _fleet.zones(), 'site': _site.site_id}


@app.get('/v1/fleet/devices/{device_id}', dependencies=[Depends(check_key)])
def fleet_device(device_id: str):
    value = _fleet.latest(device_id)
    if not value:
        raise HTTPException(status_code=404, detail='Dispositivo no encontrado')
    return value


@app.get('/v1/fleet/devices/{device_id}/history', dependencies=[Depends(check_key)])
def history(device_id: str, limit: int = Query(default=100, ge=1, le=1000)):
    return {'device_id': device_id, 'records': _fleet.repository.history(device_id, limit=limit)}


@app.get('/v1/fleet/devices/{device_id}/events', dependencies=[Depends(check_key)])
def device_events(device_id: str, limit: int = Query(default=100, ge=1, le=1000)):
    return {'device_id': device_id,
            'events': _fleet.repository.device_events(device_id, limit=limit)}


@app.get('/v1/fleet/devices/{device_id}/export.csv', dependencies=[Depends(check_key)])
def export_history(device_id: str, limit: int = Query(default=1000, ge=1, le=10000)):
    from fastapi.responses import StreamingResponse
    rows = _fleet.repository.history(device_id, limit=limit)
    if not rows:
        raise HTTPException(status_code=404, detail='Dispositivo sin registros')
    stream = io.StringIO()
    fields = ['timestamp','device_id','worker_id','zone_id','simulated','temperature_c',
              'humidity_pct','wbgt_estimate_c','wbgt_status','review_state','coverage_60m',
              'battery_pct','quality_status']
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for item in reversed(rows):
        event, result = item['event'], item['result']
        inputs = result.get('inputs_selected', {})
        estimate = result.get('environmental_estimator_v18', {})
        writer.writerow({
            'timestamp': event['timestamp'], 'device_id': event['device_id'],
            'worker_id': event.get('context',{}).get('worker_id',''),
            'zone_id': event.get('context',{}).get('zone_id','unknown'),
            'simulated': bool(event.get('transport_metadata',{}).get('simulated')),
            'temperature_c': inputs.get('air_temperature_c',{}).get('value'),
            'humidity_pct': inputs.get('relative_humidity_pct',{}).get('value'),
            'wbgt_estimate_c': estimate.get('value_c'), 'wbgt_status': estimate.get('status'),
            'review_state': result.get('review_state_v23',{}).get('state'),
            'coverage_60m': result.get('exposure_timeline_v22',{}).get('coverage_of_window_fraction'),
            'battery_pct': inputs.get('battery_level_pct',{}).get('value'),
            'quality_status': result.get('engineering_quality_v19',{}).get('status'),
        })
    payload='\ufeff'+stream.getvalue()
    headers={'Content-Disposition':f'attachment; filename="heatguard_{device_id}_history.csv"'}
    return StreamingResponse(iter([payload]),media_type='text/csv; charset=utf-8',headers=headers)


@app.post('/v1/demo/generate', dependencies=[Depends(check_admin_key)])
def demo(devices: int = Query(default=6, ge=1, le=25),
         frames: int = Query(default=10, ge=1, le=100),
         scenario: bool = False, neighbors: bool = False, seed: int = 42):
    if os.environ.get('HG_ENABLE_DEMO', '0') != '1':
        raise HTTPException(status_code=403, detail='Demo deshabilitada. Configura HG_ENABLE_DEMO=1 solo en local.')
    inserted = 0
    for event in simulated_events(devices=devices, frames=frames, seed=seed):
        result = _fleet.ingest(event, use_scenario=scenario, use_neighbors=neighbors)
        if result.get('accepted'):
            inserted += 1
            live_store.put(event, result['result'])
    return {'generated': devices * frames, 'accepted': inserted, 'simulated': True,
            'safety_alerts_enabled': False, 'scenario_assumptions_enabled': scenario}


@app.post('/v1/gateway/mobile', dependencies=[Depends(check_admin_key)])
def mobile_gateway(payload: dict, scenario: bool = False):
    """Recibe {event, phone?, wearable?} ya autorizado por la futura app."""
    try:
        obj = append_gateway_sources(payload['event'], phone=payload.get('phone'),
                                     wearable=payload.get('wearable'))
        return ingest(obj, scenario=scenario)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post('/v1/research/sensitivity', dependencies=[Depends(check_admin_key)])
def research_sensitivity(payload: dict):
    """Solo investigación offline; no genera alertas ni garantiza precisión.

    Body: {"case": <JSON de config/research_case_example.json>,
           "model":"balance", "samples":200, "seed":42}
    """
    from .sensitivity import analyze
    try:
        model = payload.get('model', 'balance')
        samples = int(payload.get('samples', 200))
        if samples > 1000:
            raise ValueError('Máximo 1000 muestras por solicitud HTTP (limitar coste de cálculo)')
        return analyze(case=payload.get('case'), model=model,
                       samples=samples, seed=int(payload.get('seed', 42)))
    except (KeyError, TypeError, ValueError, RuntimeError, ArithmeticError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

# -- HeatGuard v0.18: demostración integrada (NO producto operativo) ------------
from pathlib import Path
from fastapi.responses import HTMLResponse


@app.get('/mvp', response_class=HTMLResponse)
def mvp_dashboard():
    """Panel local de ingeniería: sin autenticación de pantalla; API admite HG_API_KEY."""
    return (Path(__file__).parent / 'static' / 'mvp.html').read_text(encoding='utf-8')


@app.get('/v1/mvp/devices', dependencies=[Depends(check_key)])
def mvp_devices():
    rows = _fleet.latest()
    items = []
    for row in rows:
        event, estimate = row['event'], row['result']
        inputs = estimate.get('inputs_selected', {})
        discrete_events = _fleet.repository.device_events(event['device_id'], limit=25)
        hydration_events = [item for item in discrete_events
                            if item.get('event_type') == 'hydration_self_report']
        age_seconds = max(0.0, (datetime.now(timezone.utc) - iso_datetime(event['timestamp'])).total_seconds())
        items.append({
            'device_id': event['device_id'],
            'worker_id': event['context'].get('worker_id'),
            'zone_id': estimate['zone_id'],
            'timestamp': event['timestamp'],
            'simulated': bool(event.get('transport_metadata', {}).get('simulated', False)),
            'temperature_c': inputs.get('air_temperature_c', {}).get('value'),
            'humidity_pct': inputs.get('relative_humidity_pct', {}).get('value'),
            'battery_pct': inputs.get('battery_level_pct', {}).get('value'),
            'steps_since_boot': inputs.get('steps_since_boot', {}).get('value'),
            'acceleration_magnitude_g': inputs.get('acceleration_magnitude_g', {}).get('value'),
            'hydration_self_report_count': len(hydration_events),
            'last_hydration_self_report': hydration_events[0] if hydration_events else None,
            'recent_device_events': discrete_events[:10],
            'connectivity': {'state': 'connected_recently' if age_seconds <= 15 else 'stale_or_disconnected',
                             'sample_age_seconds': round(age_seconds, 1),
                             'threshold_seconds': 15,
                             'not_a_radio_link_measurement': True},
            'radiative_delta_c': inputs.get('radiative_delta_c', {}).get('value'),
            'environment': event['context'].get('environment', 'unknown'),
            'estimated_wbgt': estimate.get('environmental_estimator_v18', {}),
            'engineering_quality': estimate.get('engineering_quality_v19', {}),
            'radiation': estimate.get('radiative_context_v22',{}),
            'decision_support': estimate.get('decision_support_v22', {}),
            'review_state': estimate.get('review_state_v23', {}),
            'exposure_timeline': estimate.get('exposure_timeline_v22', {}),
            'occupational_context': estimate.get('occupational_research',{}).get('context_model',{}),
            'input_contradictions': estimate.get('input_contradictions', []),
            'measurement_sources': {k: {'kind': v['kind'], 'source': v['source']}
                                    for k, v in inputs.items()},
            'occupational_alerts_enabled': False,
        })
    items.sort(key=lambda x: x['device_id'])
    return {'devices': items, 'count': len(items), 'safety_alerts_enabled': False,
            'explanation': 'Investigación y demostración. NO reemplaza instrumento WBGT de faena.'}


@app.post('/v1/mvp/demo', dependencies=[Depends(check_admin_key)])
def mvp_demo(devices: int = Query(default=4, ge=1, le=12),
             frames: int = Query(default=1, ge=1, le=20),
             research_threshold_c: float = Query(default=28.0, ge=10, le=50),
             research_half_width_c: float = Query(default=1.5, ge=0, le=10)):
    if os.environ.get('HG_ENABLE_DEMO', '0') != '1':
        raise HTTPException(status_code=403, detail='Activa explícitamente HG_ENABLE_DEMO=1 en entorno local.')
    accepted = 0
    hydration_events = 0
    seen_devices: dict[str, str] = {}
    from uuid import uuid4
    demo_run_id = uuid4().hex[:12]
    for event in simulated_events(devices=devices, frames=frames, interval_s=60):
        # Anotaciones de investigación EXPLÍCITAMENTE SIMULADAS (v0.22).
        event['context']['research_review'] = {
            'enabled': True, 'threshold_c': research_threshold_c,
            'illustrative_half_width_c': research_half_width_c,
            'duration_review_min': 5, 'origin': 'VIRTUAL_RESEARCH_EXAMPLE_NOT_OCCUPATIONAL_LIMIT'}
        sun = event['context'].get('zone_id') == 'exterior_sol'
        event['context']['radiation'] = {
            'mode':'differential','black_surface_c': 39.0 if sun else 31.0,
            'white_surface_c': 31.0 if sun else 29.0,
            'source_kind': 'assumed','source_id':'VIRTUAL_DIFFERENTIAL_NOT_INSTALLED'}
        # El generador usa secuencias repetibles. Evitar deduplicar dos clics.
        event['event_id'] = f"demo-{demo_run_id}-{event['event_id']}"
        result = _fleet.ingest(event, use_scenario=True)
        if result.get('accepted'):
            accepted += 1
            seen_devices[event['device_id']] = event['timestamp']
            live_store.put(event, result['result'])
    # Demuestra el contrato discreto del botón sin mezclarlo con observaciones.
    for index, (device_id, timestamp) in enumerate(sorted(seen_devices.items())[:2], start=1):
        outcome = _fleet.ingest_device_event({
            'event_id': f'demo-{demo_run_id}-{device_id}-hydration-{index}',
            'device_id': device_id, 'timestamp': timestamp,
            'event_type': 'hydration_self_report', 'source': 'VIRTUAL_BUTTON_0007',
            'self_reported': True, 'physiological_measurement': False,
            'metadata': {'simulated': True, 'counter': index,
                         'meaning': 'pulsación larga simulada; no mide hidratación corporal'},
        })
        hydration_events += int(outcome['accepted'])
    return {'accepted': accepted, 'simulated': True,
            'hydration_events': hydration_events,
            'has_real_clip_measurements': False, 'safety_alerts_enabled': False}
