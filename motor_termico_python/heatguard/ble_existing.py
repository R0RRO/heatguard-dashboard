"""Receptor del firmware REAL de R0RRO/heatguard-dashboard.

Firmware objetivo: panel_pruebas/firmware/heatguard_demo/heatguard_demo.ino
Protocolo fijo GATT: temperatura/humedad *100, batería %, IMU <IhhhH.
No presupone JSON por BLE. Las observaciones mantienen su procedencia.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
import os
import struct
import sys
from urllib.parse import urlsplit, urlunsplit

from .gateway_delivery import (GatewayDelivery, HttpJsonTransport,
                               configured_gateway_api_key)
from .pipeline import evaluate
from .schema import Observation
from .storage import save_record
from .weather import WeatherProvider

# UUID extraídos del firmware heatguard_demo.ino, branch main, revisado 11-11-2026.
TEMP_UUID = '00002a6e-0000-1000-8000-00805f9b34fb'
HUM_UUID = '00002a6f-0000-1000-8000-00805f9b34fb'
BAT_UUID = '00002a19-0000-1000-8000-00805f9b34fb'
PACKET_UUID = '7a1e0004-4865-6174-4775-617264436c70'
LED_UUID = '7a1e0005-4865-6174-4775-617264436c70'
MOTOR_UUID = '7a1e0006-4865-6174-4775-617264436c70'
BUTTON_UUID = '7a1e0007-4865-6174-4775-617264436c70'
CHARACTERS = (TEMP_UUID, HUM_UUID, BAT_UUID, PACKET_UUID)
NOTIFY_CHARACTERISTICS = (*CHARACTERS, BUTTON_UUID)


def decode_notification(uuid: str, data: bytes) -> dict[str, float | int]:
    """Decodificación little endian, idéntica al código JS de demo_ble."""
    uuid = uuid.lower()
    if uuid == TEMP_UUID:
        if len(data) != 2:
            raise ValueError('Temperatura BLE requiere exactamente 2 bytes')
        result = {'air_temperature_c': struct.unpack('<h', data)[0] / 100.0}
    elif uuid == HUM_UUID:
        if len(data) != 2:
            raise ValueError('Humedad BLE requiere exactamente 2 bytes')
        result = {'relative_humidity_pct': struct.unpack('<H', data)[0] / 100.0}
    elif uuid == BAT_UUID:
        if len(data) != 1:
            raise ValueError('Batería BLE requiere exactamente 1 byte')
        result = {'battery_level_pct': data[0]}
    elif uuid == PACKET_UUID:
        if len(data) != 12:
            raise ValueError('Paquete IMU requiere exactamente 12 bytes')
        steps, yaw, pitch, roll, mag = struct.unpack('<IhhhH', data)
        result = {
            'steps_since_boot': steps,
            'heading_relative_deg': yaw / 10.0,
            'pitch_deg': pitch / 10.0,
            'roll_deg': roll / 10.0,
            'acceleration_magnitude_g': mag / 1000.0,
        }
    else:
        raise ValueError(f'UUID no contemplado por heatguard_demo: {uuid}')
    # Validación la hace Observation.from_dict al crear eventos;
    # comprobar tempranamente en cada NOTIFY también.
    for name, value in result.items():
        if not math.isfinite(value):
            raise ValueError(f'Dato inválido: {name}')
    return result


def decode_button_notification(data: bytes) -> dict[str, int | bool | str]:
    """Decodifica 0007: presionado, último evento y contador uint16 LE."""
    if len(data) != 4:
        raise ValueError('Botón BLE requiere exactamente 4 bytes')
    pressed, event_code, counter = struct.unpack('<BBH', data)
    if pressed not in (0, 1):
        raise ValueError('Estado de botón BLE inválido')
    if event_code not in (0, 1, 2):
        raise ValueError('Tipo de evento de botón BLE inválido')
    return {
        'pressed': bool(pressed),
        'event_code': event_code,
        'event_name': {0: 'none', 1: 'short_press', 2: 'long_press'}[event_code],
        'counter': counter,
    }


def encode_led_command(red: int, green: int, blue: int) -> bytes:
    values = (red, green, blue)
    if any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 255 for v in values):
        raise ValueError('LED requiere tres enteros entre 0 y 255')
    return bytes(values)


def encode_motor_command(intensity: int, duration_deciseconds: int) -> bytes:
    values = (intensity, duration_deciseconds)
    if any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 255 for v in values):
        raise ValueError('Motor requiere intensidad y duración entre 0 y 255')
    return bytes(values)


@dataclass
class ButtonEventTracker:
    """Convierte notificaciones en eventos idempotentes, no fisiológicos."""
    device_id: str
    _last_counter: int | None = None
    _boot_session: int = 0
    _counter_cycle: int = 0

    @classmethod
    def from_state(cls, device_id: str, state: dict | None) -> 'ButtonEventTracker':
        state = state or {}
        previous = state.get('last_counter')
        if previous is not None and (not isinstance(previous, int) or not 0 <= previous <= 65535):
            previous = None
        return cls(device_id=device_id, _last_counter=previous,
                   _boot_session=max(0, int(state.get('boot_session', 0))),
                   _counter_cycle=max(0, int(state.get('counter_cycle', 0))))

    def state(self) -> dict:
        return {'last_counter': self._last_counter, 'boot_session': self._boot_session,
                'counter_cycle': self._counter_cycle, 'protocol': 'button_0007_v1'}

    def ingest(self, data: bytes, timestamp: datetime | None = None) -> list[dict]:
        decoded = decode_button_notification(data)
        timestamp = timestamp or utcnow()
        if timestamp.tzinfo is None:
            raise ValueError('timestamp de botón requiere zona horaria')
        counter = int(decoded['counter'])
        previous = self._last_counter
        reset = False
        wrapped = False
        if previous is not None and counter < previous:
            wrapped = previous >= 65000 and counter <= 1024
            if wrapped:
                self._counter_cycle += 1
            else:
                self._boot_session += 1
                self._counter_cycle = 0
                reset = True
        if previous == counter:
            return []
        self._last_counter = counter
        now = timestamp.astimezone(timezone.utc).isoformat()
        events: list[dict] = []
        if reset:
            events.append({
                'event_id': (f'{self.device_id}:button-reset:b{self._boot_session}:'
                             f'{previous}-{counter}:{int(timestamp.timestamp()*1000)}'),
                'device_id': self.device_id, 'timestamp': now,
                'event_type': 'button_counter_reset', 'source': 'ble_gatt_button_0007',
                'self_reported': False, 'physiological_measurement': False,
                'metadata': {'previous_counter': previous, 'counter': counter,
                             'firmware_reboot_or_counter_reset': True},
            })
        event_code = int(decoded['event_code'])
        if event_code not in (1, 2):
            return events
        if previous is None:
            delta = 1
        elif reset:
            delta = max(1, counter)
        else:
            delta = (counter - previous) & 0xFFFF
        event_type = 'hydration_self_report' if event_code == 2 else 'button_short_press'
        events.append({
            'event_id': (f'{self.device_id}:button:b{self._boot_session}:'
                         f'c{self._counter_cycle}:n{counter}:t{event_code}'),
            'device_id': self.device_id, 'timestamp': now,
            'event_type': event_type, 'source': 'ble_gatt_button_0007',
            'self_reported': event_code == 2,
            'physiological_measurement': False,
            'metadata': {
                'pressed': bool(decoded['pressed']), 'event_code': event_code,
                'counter': counter, 'counter_wrapped': wrapped,
                'events_missed_before': max(0, delta - 1),
                'meaning': ('pulsación larga autodeclarada; no mide hidratación corporal'
                            if event_code == 2 else 'pulsación corta sin inferencia fisiológica'),
            },
        })
        return events


# ¡La batería es una estimación firmware del porcentaje a partir del voltaje,
# no un medidor de carga de precisión! Paso relativo -> NO es rumbo cardinal.
PARAM_META = {
    'air_temperature_c': ('degC', 'measured', 'I2C_AHT_OR_HTU_AUTODETECT'),
    'relative_humidity_pct': ('percent', 'measured', 'I2C_AHT_OR_HTU_AUTODETECT'),
    'battery_level_pct': ('percent', 'estimated', 'FIRMWARE_LINEAR_BATTERY_ESTIMATE'),
    'steps_since_boot': ('count', 'estimated', 'MPU6050_STEP_DETECTOR'),
    'heading_relative_deg': ('deg', 'estimated', 'MPU6050_GYRO_INTEGRATION'),
    'pitch_deg': ('deg', 'estimated', 'MPU6050_ORIENTATION'),
    'roll_deg': ('deg', 'estimated', 'MPU6050_ORIENTATION'),
    'acceleration_magnitude_g': ('g', 'measured', 'MPU6050_FILTERED_MAGNITUDE'),
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ExistingClipAssembler:
    """Sincroniza características notificadas en diferentes instantes.

    Solo emite un evento cuando T° y RH han llegado AMBAS desde el último evento.
    La pareja debe ser reciente y temporalmente consistente (<max_pair_age_s).
    """
    device_id: str
    zone_id: str
    environment: str = 'unknown'
    extra_context: dict = field(default_factory=dict)
    max_pair_age_s: float = 6.0
    _values: dict[str, float | int] = field(default_factory=dict)
    _times: dict[str, datetime] = field(default_factory=dict)
    _changed: set[str] = field(default_factory=set)
    _prior_steps: int | None = None

    def ingest(self, uuid: str, data: bytes, timestamp: datetime | None = None) -> dict | None:
        timestamp = timestamp or utcnow()
        if timestamp.tzinfo is None:
            raise ValueError('timestamp requiere zona horaria')
        readings = decode_notification(uuid, data)
        for name, value in readings.items():
            unit, kind, source = PARAM_META[name]
            Observation.from_dict({
                'parameter': name, 'value': value, 'unit': unit,
                'kind': kind, 'source': source,
                'timestamp': timestamp.isoformat(),
            })
            self._values[name] = value
            self._times[name] = timestamp
            if name in ('air_temperature_c', 'relative_humidity_pct'):
                self._changed.add(name)
        if 'steps_since_boot' in readings:
            steps = int(readings['steps_since_boot'])
            if self._prior_steps is not None and steps < self._prior_steps:
                # Reinicio del ESP32: no confundir con pasos negativos.
                print('AVISO: contador de pasos reiniciado en ESP32', file=sys.stderr)
            self._prior_steps = steps
        required = {'air_temperature_c', 'relative_humidity_pct'}
        if not required.issubset(self._changed):
            return None
        age = abs((self._times['air_temperature_c'] - self._times['relative_humidity_pct']).total_seconds())
        if age > self.max_pair_age_s:
            # La lectura más antigua no sirve para una pareja actual.
            older = min(required, key=lambda p: self._times[p])
            self._changed.discard(older)
            return None
        self._changed.clear()
        sample_time = max(self._times[k] for k in required)
        stamp = sample_time.astimezone(timezone.utc).isoformat()
        observations = []
        for name, value in self._values.items():
            obs_time = self._times[name]
            # Omite batería/movimiento obsoletos. Para T/RH ya se validó pareja.
            if (sample_time - obs_time).total_seconds() > 10:
                continue
            unit, kind, source = PARAM_META[name]
            observations.append(Observation.from_dict({
                'parameter': name,
                'value': value, 'unit': unit, 'kind': kind,
                'source': source, 'timestamp': obs_time.astimezone(timezone.utc).isoformat(),
            }).as_dict())
        return {
            'device_id': self.device_id,
            'timestamp': stamp,
            'context': {'zone_id': self.zone_id, 'environment': self.environment, **self.extra_context},
            'transport_metadata': {
                'transport': 'ble_gatt_binary',
                'firmware': 'heatguard_demo',
                'timestamps': 'gateway_receive_utc',
                'note': 'step count relative to reboot; heading relative with gyro drift',
            },
            'observations': observations,
        }


def simulate_packets(i: int) -> tuple[tuple[str, bytes], ...]:
    """Bytes GATT representativos de firmware real (valores de simulación)."""
    t = round((30.0 + 0.08 * math.sin(i / 3)) * 100)
    rh = round(57.0 * 100)
    paq = struct.pack('<IhhhH', i * 3, 900, -40, 80, 1020)
    return ((PACKET_UUID, paq), (BAT_UUID, b'\x54'),
            (TEMP_UUID, struct.pack('<h', t)),
            (HUM_UUID, struct.pack('<H', rh)))


def post_json(url: str, payload: dict, *, api_key: str | None = None) -> dict:
    """Compatibilidad para una entrega directa; la pasarela usa outbox durable."""
    return HttpJsonTransport(api_key=api_key).post(url, payload)


def device_events_url(telemetry_url: str) -> str:
    parts = urlsplit(telemetry_url)
    if not parts.scheme or not parts.netloc:
        raise ValueError('--api-url debe ser una URL HTTP(S) absoluta')
    return urlunsplit((parts.scheme, parts.netloc, '/v1/fleet/device-events', '', ''))


async def process_event(event: dict, args: argparse.Namespace,
                        provider: WeatherProvider | None = None) -> dict:
    if provider is not None:
        event, weather_warnings = await asyncio.to_thread(provider.enrich, event)
    else:
        weather_warnings = []
    result = evaluate(event)
    if weather_warnings:
        result['ingestion_warnings'] = weather_warnings
    if args.db:
        await asyncio.to_thread(save_record, args.db, event, result)
    if args.api_url:
        delivery: GatewayDelivery = args.delivery
        key, inserted = await asyncio.to_thread(delivery.enqueue, args.api_url, event)
        status = await asyncio.to_thread(delivery.deliver_ready)
        result['gateway_delivery_v31'] = {
            **status, 'delivery_key': key, 'newly_queued': inserted,
            'credentials_source': 'environment_only',
        }
    return result


async def process_device_events(events: list[dict], args: argparse.Namespace) -> dict:
    if not events:
        return {'queued': 0, 'delivered': 0, 'failed': 0}
    if not args.api_url:
        # Sin API no se simula persistencia: los eventos se imprimen con su límite explícito.
        return {'queued': 0, 'delivered': 0, 'failed': 0,
                'not_persisted': True, 'events': events}
    delivery: GatewayDelivery = args.delivery
    endpoint = args.events_api_url or device_events_url(args.api_url)
    queued = 0
    for event in events:
        _, inserted = await asyncio.to_thread(delivery.enqueue, endpoint, event)
        queued += int(inserted)
    status = await asyncio.to_thread(delivery.deliver_ready)
    return {'queued': queued, **status}


async def run_simulation(args: argparse.Namespace):
    assembler = build_assembler(args)
    stored_state = (args.delivery.outbox.load_device_state(args.device_id)
                    if getattr(args, 'delivery', None) else None)
    button_tracker = ButtonEventTracker.from_state(args.device_id, stored_state)
    provider = WeatherProvider() if args.weather else None
    for i in range(args.frames):
        for uuid, packet in simulate_packets(i):
            event = assembler.ingest(uuid, packet)
            if event:
                event['transport_metadata']['simulated'] = True
                for obs in event['observations']:
                    obs['kind'] = 'assumed'
                    obs['source'] = 'SIMULATED_GATT_BYTES_NOT_HARDWARE'
                result = await process_event(event, args, provider)
                print(json.dumps({'event': event, 'result': result}, ensure_ascii=False))
        if i == getattr(args, 'simulate_long_press_frame', -1):
            button_events = button_tracker.ingest(struct.pack('<BBH', 1, 2, 1))
            delivery_status = await process_device_events(button_events, args)
            if getattr(args, 'delivery', None):
                await asyncio.to_thread(args.delivery.outbox.save_device_state,
                                        args.device_id, button_tracker.state())
            print(json.dumps({'device_events': button_events, 'delivery': delivery_status},
                             ensure_ascii=False))
        if i + 1 < args.frames:
            await asyncio.sleep(args.interval)


def build_assembler(args: argparse.Namespace) -> ExistingClipAssembler:
    context = {}
    if args.latitude is not None and args.longitude is not None:
        loc = {'latitude_deg': args.latitude, 'longitude_deg': args.longitude}
        if args.utc_offset is not None:
            loc['utc_offset_hours'] = args.utc_offset
        context['location'] = loc
        model = {'wind_height_m': 10, 'averaging_minutes': 60}
        if args.urban is not None:
            model['urban'] = args.urban
        if args.temperature_gradient is not None:
            model['vertical_temperature_difference_c'] = args.temperature_gradient
        context['weather_model'] = model
    return ExistingClipAssembler(args.device_id, args.zone, args.environment, extra_context=context)


async def run_ble(args: argparse.Namespace):
    try:
        from bleak import BleakClient, BleakScanner
    except ImportError as exc:
        raise RuntimeError('Instala bleak: pip install -e ".[ble]"') from exc
    if args.scan:
        for dev in await BleakScanner.discover(timeout=7):
            print(f'{dev.name or "(sin nombre)":27} {dev.address}')
        return
    assembler = build_assembler(args)
    stored_state = (args.delivery.outbox.load_device_state(args.device_id)
                    if getattr(args, 'delivery', None) else None)
    button_tracker = ButtonEventTracker.from_state(args.device_id, stored_state)
    provider = WeatherProvider() if args.weather else None
    delay = 1
    while True:
        try:
            target = args.address
            if target is None:
                target = await BleakScanner.find_device_by_name(args.name, timeout=10)
                if target is None:
                    raise ConnectionError(f'No se encontró {args.name!r}.')
            print(f'Conectando al clip {args.name or args.address}…', file=sys.stderr)
            async with BleakClient(target, timeout=20) as client:
                delay = 1
                q: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue(maxsize=1024)
                loop = asyncio.get_running_loop()
                def enqueue(uuid: str, data: bytes):
                    try:
                        q.put_nowait((uuid, data))
                    except asyncio.QueueFull:
                        print('ADVERTENCIA: cola GATT llena; datos omitidos', file=sys.stderr)
                def notify(char, data):
                    # Bleak puede despachar desde hilo distinto; cola solo desde loop.
                    loop.call_soon_threadsafe(enqueue, char.uuid.lower(), bytes(data))
                for uuid in NOTIFY_CHARACTERISTICS:
                    await client.start_notify(uuid, notify)
                if args.manual_led is not None:
                    await client.write_gatt_char(LED_UUID, encode_led_command(*args.manual_led), response=True)
                    print('Comando LED manual enviado; no proviene del motor ocupacional.', file=sys.stderr)
                if args.manual_vibrate is not None:
                    await client.write_gatt_char(
                        MOTOR_UUID, encode_motor_command(*args.manual_vibrate), response=True)
                    print('Comando de vibración manual enviado; no proviene del motor ocupacional.', file=sys.stderr)
                print('Conectado; escuchando características GATT reales.', file=sys.stderr)
                while client.is_connected:
                    try:
                        uuid, data = await asyncio.wait_for(q.get(), timeout=3)
                    except asyncio.TimeoutError:
                        if args.api_url:
                            status = await asyncio.to_thread(args.delivery.deliver_ready)
                            if status['errors']:
                                print('Entrega API pendiente: ' + status['errors'][0], file=sys.stderr)
                        continue
                    try:
                        if uuid == BUTTON_UUID:
                            button_events = button_tracker.ingest(data)
                            delivery_status = await process_device_events(button_events, args)
                            if args.api_url:
                                await asyncio.to_thread(args.delivery.outbox.save_device_state,
                                                        args.device_id, button_tracker.state())
                            for button_event in button_events:
                                print(json.dumps({'device_event': button_event,
                                                  'delivery': delivery_status}, ensure_ascii=False))
                            continue
                        event = assembler.ingest(uuid, data)
                        if event:
                            result = await process_event(event, args, provider)
                            print(json.dumps({
                                'device_id': event['device_id'],
                                'timestamp': event['timestamp'],
                                'temperature_c': next(x['value'] for x in event['observations'] if x['parameter'] == 'air_temperature_c'),
                                'humidity_pct': next(x['value'] for x in event['observations'] if x['parameter'] == 'relative_humidity_pct'),
                                'heat_index_c': result['metrics'].get('heat_index_c'),
                                'wbgt_status': result['wbgt_outdoor_model']['status'],
                                'occupational_risk': result['occupational_risk']['status'],
                            }, ensure_ascii=False))
                    except (ValueError, OSError, TimeoutError) as exc:
                        print(f'Dato omitido o fallo de envío: {exc}', file=sys.stderr)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f'BLE falló o desconectado: {exc}', file=sys.stderr)
        print(f'Reintentando en {delay}s…', file=sys.stderr)
        await asyncio.sleep(delay)
        delay = min(30, delay * 2)
        # Evita mezclar T/RH de otra sesión después de reconexión.
        assembler = build_assembler(args)


def main():
    def rgb(value: str) -> tuple[int, int, int]:
        try:
            parts = tuple(int(x.strip()) for x in value.split(','))
        except ValueError as exc:
            raise argparse.ArgumentTypeError('Usa R,G,B con enteros 0..255') from exc
        try:
            encode_led_command(*parts)
        except (TypeError, ValueError) as exc:
            raise argparse.ArgumentTypeError(str(exc)) from exc
        return parts

    def motor(value: str) -> tuple[int, int]:
        try:
            parts = tuple(int(x.strip()) for x in value.split(','))
        except ValueError as exc:
            raise argparse.ArgumentTypeError('Usa intensidad,duración_décimas') from exc
        try:
            encode_motor_command(*parts)
        except (TypeError, ValueError) as exc:
            raise argparse.ArgumentTypeError(str(exc)) from exc
        return parts

    p = argparse.ArgumentParser(description='HeatGuard BLE - firmware existente heatguard_demo (GATT binario)')
    p.add_argument('--simulate', action='store_true', help='Simula bytes GATT, sin clip')
    p.add_argument('--scan', action='store_true', help='Busca Bluetooth')
    p.add_argument('--name', default='HeatGuard Clip')
    p.add_argument('--address', default=None)
    p.add_argument('--device-id', default='HG-001')
    p.add_argument('--zone', default='unknown')
    p.add_argument('--environment', choices=('unknown', 'indoor', 'outdoor'), default='unknown')
    p.add_argument('--frames', type=int, default=5)
    p.add_argument('--interval', type=float, default=2.0)
    p.add_argument('--api-url', default=os.environ.get('HG_GATEWAY_API_URL'),
                   help='POST /v1/live/ingest; también puede usar HG_GATEWAY_API_URL')
    p.add_argument('--events-api-url', default=os.environ.get('HG_GATEWAY_EVENTS_API_URL'),
                   help='Endpoint de eventos; predeterminado /v1/fleet/device-events del mismo host')
    p.add_argument('--outbox', default=os.environ.get(
        'HG_GATEWAY_OUTBOX_PATH', 'data/heatguard_gateway_outbox.sqlite'),
        help='SQLite durable para reintentos y deduplicación')
    p.add_argument('--db', default=None, help='SQLite opcional')
    p.add_argument('--weather', action='store_true', help='Meteorología externa de Open-Meteo (opcional)')
    p.add_argument('--latitude', type=float)
    p.add_argument('--longitude', type=float)
    p.add_argument('--utc-offset', type=float, help='UTC local; obligatorio para modelo Liljegren')
    p.add_argument('--urban', type=int, choices=(0, 1), help='Hipótesis explícita zona urbana')
    p.add_argument('--temperature-gradient', type=float, help='Gradiente térmico supuesto en °C')
    p.add_argument('--simulate-long-press-frame', type=int, default=-1,
                   help='Solo simulación: frame que genera hidratación autodeclarada')
    p.add_argument('--allow-manual-actuators', action='store_true',
                   help='Confirma control manual de banco; nunca se activa por alertas')
    p.add_argument('--manual-led', type=rgb, metavar='R,G,B')
    p.add_argument('--manual-vibrate', type=motor, metavar='INTENSIDAD,DURACION_DS')
    args = p.parse_args()
    if args.frames < 1 or args.interval < 0:
        p.error('frames debe ser >=1 e interval >=0')
    if (args.latitude is None) != (args.longitude is None):
        p.error('Debes proporcionar latitude y longitude juntas')
    if args.weather and (args.environment != 'outdoor' or args.latitude is None):
        p.error('--weather requiere --environment outdoor y --latitude/--longitude')
    if (args.manual_led is not None or args.manual_vibrate is not None) and not args.allow_manual_actuators:
        p.error('--manual-led/--manual-vibrate requieren --allow-manual-actuators')
    if args.simulate_long_press_frame >= args.frames:
        p.error('--simulate-long-press-frame debe ser menor que --frames')
    args.delivery = (GatewayDelivery(args.outbox, api_key=configured_gateway_api_key())
                     if args.api_url else None)
    try:
        asyncio.run(run_simulation(args) if args.simulate else run_ble(args))
    except KeyboardInterrupt:
        print('Pasarela detenida', file=sys.stderr)


if __name__ == '__main__':
    main()
