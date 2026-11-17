"""Gemelo digital sin hardware: simula tramas GATT exactas del firmware heatguard_demo.

Todas las observaciones son assumed/simulated, jamás measured.
"""
from __future__ import annotations
import argparse
import json
import math
import random
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .ble_existing import ExistingClipAssembler, PACKET_UUID, BAT_UUID, TEMP_UUID, HUM_UUID
from .gateway_delivery import HttpJsonTransport, configured_gateway_api_key
from .fleet import FleetService
from .scenarios import SiteScenario, load_scenario


SITE_EXAMPLE = SiteScenario(
    site_id='FAENA_FICTICIA', latitude_deg=-33.45, longitude_deg=-70.65,
    utc_offset_hours=-3, assumed_wind_m_s=1.0,
    assumed_solar_w_m2=550.0, assumed_pressure_hpa=1013.25,
    urban=1, vertical_temperature_difference_c=0.0,
)
ZONES = ('exterior_sol', 'exterior_sombra', 'interior')


def simulated_events(*, devices: int = 6, frames: int = 30, seed: int = 42,
                     interval_s: int = 2, start: datetime | None = None):
    """Cada frame ~2 s. Generador determinista si se fija start y seed."""
    if not (1 <= devices <= 100 and 1 <= frames <= 10000 and interval_s > 0):
        raise ValueError('devices [1,100], frames [1,10000], interval_s>0')
    rng = random.Random(seed)
    start = start or datetime.now(timezone.utc).replace(microsecond=0)
    if start.tzinfo is None:
        raise ValueError('start requiere zona horaria')
    assemblers = []
    for d in range(devices):
        zone = ZONES[d % len(ZONES)]
        a = ExistingClipAssembler(
            device_id=f'HG-{d + 101:04d}', zone_id=zone,
            environment='indoor' if zone == 'interior' else 'outdoor',
            extra_context={
                'worker_id': f'virtual-worker-{d + 1:02d}',
                'site_id': SITE_EXAMPLE.site_id,
                'activity_class': ('light', 'moderate', 'heavy')[d % 3],
                'work_state': 'working',
                'activity_source': 'virtual_scenario_not_accelerometer',
                'clothing': 'unknown', 'acclimatization': 'unknown',
            },
        )
        assemblers.append(a)
    for frame in range(frames):
        tstamp = start + timedelta(seconds=frame * interval_s)
        for idx, assembler in enumerate(assemblers):
            zone = assembler.zone_id
            temp = (31.5 if zone == 'exterior_sol' else 28.7 if zone == 'exterior_sombra' else 29.4)
            rh = (47 if zone == 'exterior_sol' else 54 if zone == 'exterior_sombra' else 62)
            temp += 0.8 * math.sin(frame / 15) + rng.uniform(-0.12, 0.12)
            rh += 0.8 * math.cos(frame / 13) + rng.uniform(-0.3, 0.3)
            steps = frame * (2 + idx % 3)
            movement = struct.pack('<IhhhH', steps, (frame * 4) % 3600, -30, 50, 1000 + idx * 5)
            packets = (
                (PACKET_UUID, movement),
                (BAT_UUID, bytes([max(1, 94 - frame // 300)])),
                (TEMP_UUID, struct.pack('<h', round(temp * 100))),
                (HUM_UUID, struct.pack('<H', round(rh * 100))),
            )
            for uuid, data in packets:
                event = assembler.ingest(uuid, data, timestamp=tstamp)
                if event is None:
                    continue
                event['event_id'] = f'{assembler.device_id}-{frame:06d}'
                event['transport_metadata']['simulated'] = True
                event['transport_metadata']['simulation_type'] = 'binary_gatt_virtual_clip'
                event['transport_metadata']['source'] = 'offline_digital_twin'
                for obs in event['observations']:
                    obs['kind'] = 'assumed'
                    obs['source'] = 'VIRTUAL_GATT_NOT_REAL_SENSOR'
                    obs['metadata'] = {'simulated': True,
                                       'original_firmware_derived': True}
                yield event


def _post(url: str, event: dict, *, use_scenario: bool = False) -> dict:
    # Los switches se pasan por query, no dentro de una lectura instrumental.
    if use_scenario:
        url += ('&' if '?' in url else '?') + 'scenario=true'
    return HttpJsonTransport(api_key=configured_gateway_api_key(), timeout_s=10).post(url, event)


def main():
    parser = argparse.ArgumentParser(description='HeatGuard: faena digital sin ESP32')
    parser.add_argument('--devices', type=int, default=6)
    parser.add_argument('--frames', type=int, default=30)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--interval', type=int, default=2)
    parser.add_argument('--db', default='data/heatguard_v04.sqlite')
    parser.add_argument('--scenario-file', default='', help='JSON explícito de hipótesis del sitio')
    parser.add_argument('--api-url', default='')
    parser.add_argument('--with-scenario', action='store_true', help='Añadir hipótesis explícitas para viento/radiación/presión exterior')
    parser.add_argument('--neighbors', action='store_true', help='Completar T/RH faltantes con vecinos de misma zona (experimental)')
    parser.add_argument('--out-jsonl', default='')
    args = parser.parse_args()
    site = load_scenario(args.scenario_file, SITE_EXAMPLE)
    fleet = FleetService(db_path=args.db, scenario=site)
    written = 0
    destination = Path(args.out_jsonl) if args.out_jsonl else None
    if destination:
        destination.parent.mkdir(parents=True, exist_ok=True)
    sink = destination.open('w', encoding='utf-8') if destination else None
    try:
        for event in simulated_events(devices=args.devices, frames=args.frames,
                                      seed=args.seed, interval_s=args.interval):
            if sink:
                sink.write(json.dumps(event, ensure_ascii=False) + '\n')
            if args.api_url:
                resp = _post(args.api_url, event, use_scenario=args.with_scenario)
            else:
                resp = fleet.ingest(event, use_scenario=args.with_scenario,
                                    use_neighbors=args.neighbors)
            if resp.get('accepted'):
                written += 1
        print(json.dumps({'generated_events': args.devices * args.frames,
                          'new_events': written, 'database': args.db if not args.api_url else 'API remota',
                          'hypotheses_enabled': args.with_scenario,
                          'model_reality': '100% SIMULATED - no physical measurements'}, ensure_ascii=False))
        if not args.api_url:
            print(json.dumps(fleet.fleet_summary(), ensure_ascii=False, indent=2)[:5000])
    finally:
        if sink:
            sink.close()


if __name__ == '__main__':
    main()
