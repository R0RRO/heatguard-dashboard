"""Adaptador explícito contrato lógico v2 del repositorio React/Android -> backend Python.

NO usa radio ni escribe BLE. NO reemplaza el firmware ni el backend Node.
NO rellena viento/radiación ni reinterpreta Heat Index como WBGT.

Payload esperado: docs/contrato-datos.md (R0RRO/heatguard-dashboard, rama main).
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import math
from typing import Any


def _number(value: Any, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} requiere un número finito")
    result = float(value)
    if not (low <= result <= high):
        raise ValueError(f"{name} fuera de rango {low}..{high}")
    return result


def _integer(value: Any, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not (low <= value <= high):
        raise ValueError(f"{name} fuera de rango o no es entero")
    return value


def convert_v2_to_heatguard_event(
    packet: dict,
    *,
    zone_id: str = "unknown",
    environment: str = "unknown",
    simulated: bool = True,
    worker_pseudonym: str | None = None,
    extra_environment: list[dict] | None = None,
) -> dict:
    """Convierte SOLO contrato JSON v2; no bytes GATT.

    simulated=True por defecto: una prueba nunca se etiqueta accidentalmente como real.
    `extra_environment`: observaciones externas explícitas con kind, unit, source,
    timestamp y calidad; NO se completan por defecto.
    """
    if not isinstance(packet, dict) or packet.get("v") != 2 or isinstance(packet.get("v"), bool):
        raise ValueError("Se requiere contrato lógico v2")
    dev=packet.get("deviceId")
    if not isinstance(dev,str) or not dev.strip() or len(dev)>120:
        raise ValueError("deviceId inválido")
    _integer(packet.get("seq"),"seq",0,65535)
    ms=_integer(packet.get("receivedAt"),"receivedAt",946684800000,4102444800000)
    if not isinstance(zone_id,str) or not zone_id.strip():
        raise ValueError("zone_id obligatorio")
    if environment not in ("outdoor","indoor","unknown"):
        raise ValueError("environment inválido")
    for key in ("env","motion","battery"):
        if not isinstance(packet.get(key),dict):
            raise ValueError(f"{key} requiere objeto")
    env,motion,battery=packet["env"],packet["motion"],packet["battery"]
    timestamp=datetime.fromtimestamp(ms/1000,timezone.utc).isoformat()
    observations=[]
    kind="assumed" if simulated else "measured"
    source="V2_SIMULATED_CLIP" if simulated else "V2_CLIP_RELAY_DECLARED"
    def obs(parameter: str, value: float, unit: str):
        observations.append({"parameter":parameter,"value":value,"unit":unit,
            "kind":kind,"source":source,"quality":"unverified","timestamp":timestamp})
    if env.get("ok") is True:
        obs("air_temperature_c",_number(env.get("tempC"),"env.tempC",-40,80),"degC")
        obs("relative_humidity_pct",_number(env.get("rhPct"),"env.rhPct",0,100),"percent")
    if motion.get("ok") is True and motion.get("index") is not None:
        # Índice 0-100 NO es aceleración RMS [g], ni clase metabólica.
        obs("motion_index_v2",_number(motion["index"],"motion.index",0,100),"index_0_100")
    if battery.get("pct") is not None:
        obs("battery_level_pct",_number(battery["pct"],"battery.pct",0,100),"percent")
    if extra_environment is not None:
        if not isinstance(extra_environment,list):
            raise ValueError("extra_environment debe ser lista de observaciones con origen")
        for item in extra_environment:
            if not isinstance(item,dict) or item.get('kind') not in ('external','measured','estimated','assumed') or not item.get('source') or not item.get('timestamp'):
                raise ValueError("Dato externo sin source, timestamp y kind: no se puede completar automáticamente")
            if item.get('parameter') in {o['parameter'] for o in observations}:
                raise ValueError("No sobrescribir medidas locales desde fuente externa")
            observations.append(dict(item))
    context={
        "zone_id":zone_id,"environment":environment,
        "v2_seq":packet['seq'],
        "clip_load_pct_unvalidated":packet.get("load"),
        "clip_state_code_v2":packet.get("state"),
        "clip_pauses_since_boot":packet.get("pauses"),
        "clip_heat_index_c_non_wbgt":env.get("heatIndexC"),
        "button_is_pressed_not_hydration_event": bool((packet.get("button") or {}).get("pressed",False)),
        "source_contract":"dashboard_firmware_v2_20_bytes",
        "work_state":"unknown",
        "activity_class":"unknown",
    }
    if worker_pseudonym is not None:
        if not isinstance(worker_pseudonym,str) or not worker_pseudonym.strip():
            raise ValueError("worker_pseudonym inválido")
        context['worker_id']=worker_pseudonym.strip()
    event_id=sha256(f"{dev.strip()}|{ms}|{packet['seq']}".encode()).hexdigest()[:28]
    return {
        "event_id": f"v2-{event_id}",
        "device_id":dev.strip(),
        "timestamp":timestamp,
        "context":context,
        "observations":observations,
        "transport_metadata":{"simulated":bool(simulated),
                              "source_transport":"v2_json_adapter_not_ble_physical_test",
                              "contract_version":2}
    }
