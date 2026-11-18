"""Servicio WBGT para Node: lote con meteorología simulada (sin red)."""
import json
import threading
import urllib.request

from heatguard.ono_v09 import wbgt_ono
from heatguard.weather import WeatherProvider
from integracion.servicio_wbgt import MotorWbgt, crear_servidor, nivel_wbgt

METEO = {"hourly": {
    "time": ["2026-11-18T17:00", "2026-11-18T18:00"],
    "temperature_2m": [29.0, 30.0], "relative_humidity_2m": [30, 28], "surface_pressure": [950, 950],
    "wind_speed_10m": [2.0, 3.0], "shortwave_radiation": [700.0, 850.0],
}}


def motor(datos=METEO):
    return MotorWbgt(WeatherProvider(fetch=lambda url: datos))


def test_niveles():
    assert nivel_wbgt(20.9) == (0, "Casi seguro")
    assert nivel_wbgt(21.0)[0] == 1
    assert nivel_wbgt(27.9)[0] == 2
    assert nivel_wbgt(30.0)[0] == 3
    assert nivel_wbgt(35.0) == (4, "Peligro")


def test_lote_usa_ono_con_la_hora_meteorologica_correspondiente():
    r = motor().lote({"lat": -33.4, "lon": -70.6, "items": [
        {"id": "w1", "tempC": 31.0, "rhPct": 40, "timestamp": "2026-11-18T18:20:00Z"},
        {"id": "w2", "tempC": 31.0, "rhPct": 40, "timestamp": "2026-11-18T17:30:00Z"},
    ]})
    w1, w2 = r["items"]
    assert w1["status"] == "ok" and w1["solarWm2"] == 850 and w1["windMs"] == 3.0
    assert w1["wbgtC"] == round(wbgt_ono(31.0, 40, 850.0, 3.0), 1)
    assert w2["solarWm2"] == 700           # otra hora, otra radiación
    assert w1["level"] == nivel_wbgt(w1["wbgtC"])[0]


def test_sin_meteorologia_no_inventa_valores():
    def falla(url):
        raise OSError("sin red")
    r = MotorWbgt(WeatherProvider(fetch=falla)).lote({"lat": -33.4, "lon": -70.6, "items": [
        {"id": "w1", "tempC": 31.0, "rhPct": 40, "timestamp": "2026-11-18T18:20:00Z"}]})
    assert r["meteo"]["status"] == "sin_meteorologia"
    assert r["items"] == [{"id": "w1", "status": "sin_meteorologia"}]


def test_fuera_del_pronostico_o_datos_invalidos():
    r = motor().lote({"lat": -33.4, "lon": -70.6, "items": [
        {"id": "a", "tempC": 31.0, "rhPct": 40, "timestamp": "2026-11-20T18:20:00Z"},
        {"id": "b", "tempC": 99, "rhPct": 40, "timestamp": "2026-11-18T18:20:00Z"}]})
    assert [x["status"] for x in r["items"]] == ["error", "error"]


def test_http_exige_clave():
    srv = crear_servidor(motor(), "clave-de-prueba-123456", "127.0.0.1", 0)
    hilo = threading.Thread(target=srv.serve_forever, daemon=True)
    hilo.start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/v1/wbgt/lote"
    cuerpo = json.dumps({"lat": -33.4, "lon": -70.6, "items": [
        {"id": "w1", "tempC": 31.0, "rhPct": 40, "timestamp": "2026-11-18T18:20:00Z"}]}).encode()
    try:
        malo = urllib.request.Request(url, data=cuerpo, headers={"x-api-key": "otra"})
        try:
            urllib.request.urlopen(malo)
            assert False, "debía rechazar"
        except urllib.error.HTTPError as e:
            assert e.code == 401
        bueno = urllib.request.Request(url, data=cuerpo, headers={"x-api-key": "clave-de-prueba-123456"})
        r = json.load(urllib.request.urlopen(bueno))
        assert r["items"][0]["status"] == "ok"
    finally:
        srv.shutdown()
