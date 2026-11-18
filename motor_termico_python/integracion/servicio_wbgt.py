"""Servicio WBGT para el servidor HeatGuard (Node).

Puente backend-backend descrito en integracion/CONTRATO_Y_PENDIENTES.md: Node envía la temperatura y
humedad de cada trabajador (clip real o simulado) y este servicio responde el WBGT estimado con el modelo
de Ono (heatguard/ono_v09.py), usando radiación solar y viento del pronóstico regional Open-Meteo
(heatguard/weather.py). Solo biblioteca estándar de Python; escucha en 127.0.0.1 y exige clave.

    HG_WBGT_KEY=... python3 -m integracion.servicio_wbgt      (desde motor_termico_python/)

Variables: HG_WBGT_KEY (obligatoria), HG_WBGT_PORT (8790), HG_WBGT_HOST (127.0.0.1).

POST /v1/wbgt/lote   (cabecera X-API-Key)
    {"lat": -33.415, "lon": -70.6, "items": [{"id": "w1", "tempC": 31.4, "rhPct": 48, "timestamp": "2026-11-18T18:30:00Z"}]}
 -> {"meteo": {...}, "items": [{"id": "w1", "status": "ok", "wbgtC": 27.9, "level": 2, "label": "Advertencia",
                                "solarWm2": 812, "windMs": 2.4, "meteoTimestamp": "..."}]}

El resultado es una ESTIMACIÓN de modelo con meteorología regional: no es WBGT/TGBH medido ni ISO 7243.
"""
from __future__ import annotations

import hmac
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from heatguard.ono_v09 import wbgt_ono
from heatguard.weather import WeatherProvider, parse_openmeteo

# Niveles de WBGT (°C) de la guía del Ministerio de Medio Ambiente de Japón, usada por el modelo de Ono.
# En HeatGuard cada nivel define el factor de calor de la exposición acumulada (regla del prototipo, sin validar).
NIVELES = [
    (21.0, "Casi seguro"),
    (25.0, "Atención"),
    (28.0, "Advertencia"),
    (31.0, "Advertencia severa"),
    (float("inf"), "Peligro"),
]
MAX_ITEMS = 200


def nivel_wbgt(wbgt_c: float) -> tuple[int, str]:
    for i, (limite, nombre) in enumerate(NIVELES):
        if wbgt_c < limite:
            return i, nombre
    return len(NIVELES) - 1, NIVELES[-1][1]


def _numero(v, nombre, lo, hi):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not (lo <= v <= hi):
        raise ValueError(f"{nombre} fuera de rango")
    return float(v)


class MotorWbgt:
    """Calcula el WBGT de un lote; la respuesta meteorológica se reutiliza (caché de 15 min)."""

    def __init__(self, provider: WeatherProvider | None = None):
        self.provider = provider or WeatherProvider(ttl_s=900)

    def lote(self, cuerpo: dict) -> dict:
        lat = _numero(cuerpo.get("lat"), "lat", -90, 90)
        lon = _numero(cuerpo.get("lon"), "lon", -180, 180)
        items = cuerpo.get("items")
        if not isinstance(items, list) or len(items) > MAX_ITEMS:
            raise ValueError("items debe ser una lista (máx. 200)")
        try:
            datos = self.provider._response(lat, lon)
            meteo = {"status": "ok", "source": "OPEN_METEO_HOURLY_MODEL"}
        except Exception as exc:  # sin red o servicio caído: Node usa la sensación térmica como respaldo
            return {"meteo": {"status": "sin_meteorologia", "detail": str(exc)[:200]},
                    "items": [{"id": it.get("id"), "status": "sin_meteorologia"} for it in items if isinstance(it, dict)]}
        cache: dict[str, dict] = {}
        salida = []
        for it in items:
            if not isinstance(it, dict):
                continue
            ident = str(it.get("id", ""))[:40]
            try:
                t = _numero(it.get("tempC"), "tempC", -40, 60)
                rh = _numero(it.get("rhPct"), "rhPct", 0, 100)
                ts = it.get("timestamp")
                hora = str(ts)[:13]   # el pronóstico es horario: misma hora, mismos datos
                if hora not in cache:
                    obs = {o["parameter"]: o for o in parse_openmeteo(datos, ts)}
                    cache[hora] = obs
                obs = cache[hora]
                solar = obs.get("solar_w_m2", {}).get("value")
                viento = obs.get("wind_speed_m_s", {}).get("value")
                if solar is None or viento is None:
                    salida.append({"id": ident, "status": "sin_meteorologia"})
                    continue
                w = wbgt_ono(t, rh, solar, viento)
                nivel, nombre = nivel_wbgt(w)
                salida.append({"id": ident, "status": "ok", "wbgtC": round(w, 1), "level": nivel, "label": nombre,
                               "solarWm2": round(solar), "windMs": round(viento, 1),
                               "meteoTimestamp": obs["solar_w_m2"]["timestamp"]})
            except (ValueError, KeyError, TypeError) as exc:
                salida.append({"id": ident, "status": "error", "detail": str(exc)[:120]})
        return {"meteo": meteo, "model": "Ono et al. (2014) + Open-Meteo", "items": salida}


def crear_servidor(motor: MotorWbgt, clave: str, host: str = "127.0.0.1", puerto: int = 8790):
    class Manejador(BaseHTTPRequestHandler):
        def _json(self, code, datos):
            cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def do_GET(self):
            if self.path == "/health":
                return self._json(200, {"status": "ok", "model": "ono_v09", "normative_measurement": False})
            return self._json(404, {"error": "No existe"})

        def do_POST(self):
            if self.path != "/v1/wbgt/lote":
                return self._json(404, {"error": "No existe"})
            if not hmac.compare_digest(self.headers.get("x-api-key", ""), clave):
                return self._json(401, {"error": "Clave inválida"})
            largo = int(self.headers.get("content-length") or 0)
            if largo > 64 * 1024:
                return self._json(413, {"error": "Demasiado grande"})
            try:
                cuerpo = json.loads(self.rfile.read(largo) or b"{}")
                return self._json(200, motor.lote(cuerpo))
            except (ValueError, json.JSONDecodeError) as exc:
                return self._json(400, {"error": str(exc)})

        def log_message(self, *args):  # sin registro por petición (Node llama cada 1,5 s)
            pass

    return ThreadingHTTPServer((host, puerto), Manejador)


def main():
    clave = os.environ.get("HG_WBGT_KEY", "")
    if len(clave) < 16:
        print("Define HG_WBGT_KEY (al menos 16 caracteres).", file=sys.stderr)
        sys.exit(1)
    host = os.environ.get("HG_WBGT_HOST", "127.0.0.1")
    puerto = int(os.environ.get("HG_WBGT_PORT", "8790"))
    srv = crear_servidor(MotorWbgt(), clave, host, puerto)
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} Servicio WBGT en http://{host}:{puerto}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
