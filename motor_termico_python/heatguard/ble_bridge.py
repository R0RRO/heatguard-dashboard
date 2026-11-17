"""Pasarela BLE ESP32-C3 -> backend HeatGuard.

PROTOCOLO PROPUESTO (no presupone que el firmware existente ya lo envíe):
Una notificación GATT puede contener fragmentos de una línea JSON terminada por \\n:
{"temperature_c":31.2,"humidity_pct":60.1,"activity_rms_g":0.08,"seq":1}\n
El receptor recompone fragmentos, valida, marca con hora UTC de recepción y
produce el contrato común de Observations. UUID y nombre se configuran por CLI.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import math
import sys
from datetime import datetime, timezone

from .gateway_delivery import HttpJsonTransport, configured_gateway_api_key
from .pipeline import evaluate
from .schema import Observation
from .storage import save_record
from .weather import WeatherProvider

MAX_FRAME_BYTES = 2048


class LineFrames:
    """Recompone JSON por línea aunque BLE fragmente los mensajes."""
    def __init__(self, max_bytes: int = MAX_FRAME_BYTES):
        self.buffer = bytearray()
        self.max_bytes = max_bytes

    def feed(self, chunk: bytes) -> list[str]:
        self.buffer.extend(chunk)
        if len(self.buffer) > self.max_bytes and b"\n" not in self.buffer:
            self.buffer.clear()
            raise ValueError("Trama BLE demasiado extensa o sin separador de línea.")
        frames = []
        while b"\n" in self.buffer:
            part, _, rest = self.buffer.partition(b"\n")
            self.buffer = bytearray(rest)
            if len(part) > self.max_bytes:
                raise ValueError("Trama BLE excede longitud máxima.")
            part = part.strip()
            if part:
                frames.append(part.decode("utf-8", errors="strict"))
        if len(self.buffer) > self.max_bytes:
            self.buffer.clear()
            raise ValueError("Buffer BLE supera longitud máxima.")
        return frames


def packet_to_event(packet: str | dict, device_id: str, zone: str,
                    context: dict | None = None, received_at: datetime | None = None) -> dict:
    """Convierte una trama del firmware en un evento del backend.

    Las claves que NO conocemos se conservan en `transport_metadata` para futura
    extensión, no se convierten silenciosamente en datos físicos. Rango inválido
    -> ValueError. No calcula viento a partir de aceleración.
    """
    if isinstance(packet, str):
        packet = json.loads(packet)
    if not isinstance(packet, dict):
        raise ValueError("La trama BLE debe ser un objeto JSON.")
    stamp = (received_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    mapping = {
        "temperature_c": ("air_temperature_c", "degC"),
        "humidity_pct": ("relative_humidity_pct", "percent"),
        "activity_rms_g": ("activity_rms_g", "g"),
        "surface_temperature_c": ("surface_temperature_c", "degC"),
    }
    obs = []
    for key, (parameter, unit) in mapping.items():
        if key in packet:
            item = Observation.from_dict({
                "parameter": parameter, "value": packet[key], "unit": unit,
                "kind": "measured", "source": "ESP32_C3_BLE",
                "timestamp": stamp,
            })
            obs.append(item.as_dict())
    if not any(x["parameter"] == "air_temperature_c" for x in obs):
        raise ValueError("Trama sin temperature_c.")
    if not any(x["parameter"] == "relative_humidity_pct" for x in obs):
        raise ValueError("Trama sin humidity_pct.")
    metadata = {k: v for k, v in packet.items() if k not in mapping}
    return {
        "device_id": device_id, "timestamp": stamp,
        "context": {"zone_id": zone, **(copy.deepcopy(context) if context else {})},
        "transport_metadata": {"transport": "ble", "extra": metadata},
        "observations": obs,
    }


def _post_json(url: str, payload: dict, timeout: int = 5) -> dict:
    return HttpJsonTransport(api_key=configured_gateway_api_key(), timeout_s=timeout).post(url, payload)


async def evaluate_and_send(event: dict, *, api_url: str | None, db_path: str | None,
                            weather_provider: WeatherProvider | None) -> dict:
    warnings = []
    if weather_provider is not None:
        event, warnings = await asyncio.to_thread(weather_provider.enrich, event)
    # Pipeline puro: NO solicita red ni usa datos ocultos.
    result = evaluate(event)
    if warnings:
        result["ingestion_warnings"] = warnings
    if db_path:
        await asyncio.to_thread(save_record, db_path, event, result)
    if api_url:
        # Se envía el evento enriquecido para que servidor lo reprocese con igual origen.
        await asyncio.to_thread(_post_json, api_url, event)
    return result


def _base_context(args: argparse.Namespace) -> dict:
    context: dict = {"environment": args.environment}
    if args.latitude is not None and args.longitude is not None:
        context["location"] = {
            "latitude_deg": args.latitude,
            "longitude_deg": args.longitude,
        }
        if args.utc_offset is not None:
            context["location"]["utc_offset_hours"] = args.utc_offset
        context["weather_model"] = {"wind_height_m": 10, "averaging_minutes": 60}
        if args.urban is not None:
            context["weather_model"]["urban"] = args.urban
        if args.temperature_gradient is not None:
            context["weather_model"]["vertical_temperature_difference_c"] = args.temperature_gradient
    return context


async def run_simulation(args: argparse.Namespace) -> None:
    provider = WeatherProvider() if args.weather else None
    for i in range(args.frames):
        sample = {
            "temperature_c": round(31.0 + 0.3 * math.sin(i / 4), 2),
            "humidity_pct": 57.0,
            "activity_rms_g": round(0.08 + 0.03 * abs(math.sin(i)), 3),
            "seq": i,
        }
        event = packet_to_event(sample, args.device_id, args.zone, _base_context(args))
        result = await evaluate_and_send(event, api_url=args.api_url,
                                         db_path=args.db, weather_provider=provider)
        print(json.dumps({"event": event, "result": result}, ensure_ascii=False))
        if i + 1 < args.frames:
            await asyncio.sleep(args.interval)


async def run_ble(args: argparse.Namespace) -> None:
    try:
        from bleak import BleakClient, BleakScanner
    except ImportError as exc:
        raise RuntimeError("Instala el extra BLE: python -m pip install -e '.[ble]' ") from exc

    if args.scan:
        for device in await BleakScanner.discover(timeout=8):
            print(f"{device.name or '(sin nombre)':28s} {device.address}")
        return
    if not args.char_uuid:
        raise ValueError("Indica --char-uuid del firmware (característica NOTIFY).")
    if not args.address and not args.name:
        raise ValueError("Indica --address o --name; usar --scan para descubrir dispositivos.")
    provider = WeatherProvider() if args.weather else None
    retry = 1
    while True:
        try:
            target = args.address
            if not target:
                target = await BleakScanner.find_device_by_name(args.name, timeout=10)
                if target is None:
                    raise ConnectionError(f"No se detectó el dispositivo {args.name!r}.")
            print(f"Conectando a {args.name or args.address}...", file=sys.stderr)
            async with BleakClient(target, timeout=20) as client:
                q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=150)
                parser = LineFrames()
                def on_notify(_sender, data: bytearray):
                    try:
                        q.put_nowait(bytes(data))
                    except asyncio.QueueFull:
                        print("ADVERTENCIA: cola BLE llena, se descartó un paquete.", file=sys.stderr)
                await client.start_notify(args.char_uuid, on_notify)
                print("BLE conectado. Escuchando notificaciones...", file=sys.stderr)
                retry = 1
                while client.is_connected:
                    try:
                        chunk = await asyncio.wait_for(q.get(), timeout=3)
                    except asyncio.TimeoutError:
                        continue
                    try:
                        lines = parser.feed(chunk)
                        for line in lines:
                            event = packet_to_event(line, args.device_id, args.zone, _base_context(args))
                            result = await evaluate_and_send(event, api_url=args.api_url,
                                                             db_path=args.db, weather_provider=provider)
                            print(json.dumps({"event": event, "result": result}, ensure_ascii=False))
                    except (ValueError, json.JSONDecodeError, UnicodeError) as exc:
                        print(f"Trama inválida, descartada: {exc}", file=sys.stderr)
                    except (OSError, TimeoutError) as exc:
                        print(f"No se pudo enviar/guardar: {exc}", file=sys.stderr)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"BLE desconectado o falló: {exc}", file=sys.stderr)
        print(f"Reintento BLE en {retry}s...", file=sys.stderr)
        await asyncio.sleep(retry)
        retry = min(retry * 2, 30)


def main() -> None:
    p = argparse.ArgumentParser(description="Pasarela BLE y simulación HeatGuard v0.2")
    p.add_argument("--simulate", action="store_true", help="Datos ficticios, no requiere hardware")
    p.add_argument("--scan", action="store_true", help="Buscar dispositivos BLE")
    p.add_argument("--address", help="Dirección BLE (en Windows/Linux)")
    p.add_argument("--name", help="Nombre BLE anunciado por el firmware")
    p.add_argument("--char-uuid", help="UUID de la característica NOTIFY")
    p.add_argument("--device-id", default="HG-001")
    p.add_argument("--zone", default="OBRA-EXTERIOR")
    p.add_argument("--environment", choices=("outdoor", "indoor", "unknown"), default="outdoor")
    p.add_argument("--latitude", type=float)
    p.add_argument("--longitude", type=float)
    p.add_argument("--utc-offset", type=float, help="Desfase UTC de fecha local; indicar explícitamente")
    p.add_argument("--urban", type=int, choices=(0, 1), help="Supuesto/valor conocido: 1 urbana, 0 rural")
    p.add_argument("--temperature-gradient", type=float, help="Gradiente del modelo, explícito")
    p.add_argument("--weather", action="store_true", help="Permitir consulta externa Open-Meteo")
    p.add_argument("--api-url", help="URL local POST /v1/estimate opcional")
    p.add_argument("--db", help="Ruta de SQLite opcional (datos y resultados)")
    p.add_argument("--frames", type=int, default=3)
    p.add_argument("--interval", type=float, default=0.3)
    args = p.parse_args()
    if (args.latitude is None) != (args.longitude is None):
        p.error("Proporciona --latitude y --longitude juntos.")
    if args.frames < 1 or args.interval < 0:
        p.error("--frames debe ser >=1 y --interval >=0.")
    try:
        asyncio.run(run_simulation(args) if args.simulate else run_ble(args))
    except KeyboardInterrupt:
        print("Pasarela detenida.", file=sys.stderr)
    except (ValueError, RuntimeError) as exc:
        p.error(str(exc))


if __name__ == "__main__":
    main()
