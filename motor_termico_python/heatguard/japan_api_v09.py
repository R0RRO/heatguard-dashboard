"""Adaptador oficial de la API japonesa de WBGT: datos de referencia con Tg medida.

Fuente: Japón MOE API getSurveyData, manual v1.1 (2026-06-24):
https://www.wbgt.env.go.jp/man15NH/wbgt_data_api_service_manual.pdf

Admisión estricta: wbgt_class==1 y wbgt_WI==4. Este indicador significa
observaciones meteorológicas y de globo completas; Tw sigue siendo CALCULADA.
No se equipara a medición ISO 7243 de bulbo húmedo natural.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from datetime import datetime, timedelta, timezone, date
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_URL = 'https://www.wbgt.env.go.jp/api/v1/getSurveyData'
SOURCE_MANUAL = 'https://www.wbgt.env.go.jp/man15NH/wbgt_data_api_service_manual.pdf'
JST = timezone(timedelta(hours=9))


def build_url(station_no: int, first_day: str, last_day: str) -> str:
    station = int(station_no)
    a, b = date.fromisoformat(first_day), date.fromisoformat(last_day)
    if not 1 <= station <= 99999 or not a <= b or (b-a).days > 31:
        raise ValueError('Estación inválida o más de 32 días por petición; limitar para no saturar el servicio')
    params = {
        'data_type': 1, 'location_type': 1, 'wbgt_nos': station,
        'date_from': a.strftime('%Y%m%d') + '000000',
        'date_to': b.strftime('%Y%m%d') + '235959',
    }
    return API_URL + '?' + urlencode(params)


def fetch_json(url: str) -> dict:
    if not url.startswith(API_URL + '?'):
        raise ValueError('URL de la API oficial no reconocida')
    req = Request(url, headers={'User-Agent': 'HeatGuardResearch/0.9 (noncommercial education)', 'Accept': 'application/json'})
    with urlopen(req, timeout=30) as response:
        if response.status != 200: raise ValueError(f'HTTP {response.status}')
        data = json.load(response)
    if not isinstance(data, dict) or data.get('status') != 'success':
        raise ValueError(f'API japonesa devolvió error: {str(data)[:250]}')
    return data


def local_to_utc(value: str) -> str:
    """Convierte YYYY/MM/DD HH:MM:SS JST; soporta 24:00 si aparece."""
    text = value.strip()
    if ' 24:' in text:
        day, hour = text.split(' ', 1)
        if hour != '24:00:00': raise ValueError(f'Hora no válida: {text}')
        d = datetime.strptime(day, '%Y/%m/%d') + timedelta(days=1)
    else:
        d = datetime.strptime(text, '%Y/%m/%d %H:%M:%S')
    return d.replace(tzinfo=JST).astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def normalize_observed(obj: dict, *, station_no: int, site_id: str,
                       latitude_deg: float, longitude_deg: float) -> tuple[list[dict], dict]:
    if obj.get('status') != 'success' or not isinstance(obj.get('data'), list):
        raise ValueError('JSON no es una respuesta exitosa de getSurveyData')
    if not site_id.strip(): raise ValueError('site_id obligatorio')
    lat, lon = float(latitude_deg), float(longitude_deg)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180): raise ValueError('Coordenadas inválidas')
    accepted, counts, seen = [], {'raw': len(obj['data']), 'wrong_station': 0,
         'not_measured_station': 0, 'quality_not_4': 0, 'incomplete': 0}, set()
    for raw in obj['data']:
        if int(raw.get('wbgt_no', -1)) != int(station_no):
            counts['wrong_station'] += 1; continue
        if int(raw.get('wbgt_class', -1)) != 1:
            counts['not_measured_station'] += 1; continue
        wi = raw.get('wbgt_WI')
        try: wi = float(wi)
        except (ValueError, TypeError): wi = float('nan')
        if wi != 4.0:
            counts['quality_not_4'] += 1; continue
        try:
            ts = local_to_utc(str(raw['wbgt_date']))
            wbgt, tg, tw = (float(raw[k]) for k in ('wbgt_WO', 'wbgt_Tg', 'wbgt_Tw'))
        except (KeyError, ValueError, TypeError):
            counts['incomplete'] += 1; continue
        if not (math.isfinite(wbgt) and math.isfinite(tg) and math.isfinite(tw) and
                -30 <= wbgt <= 60 and -50 <= tg <= 95 and -50 <= tw <= 60):
            counts['incomplete'] += 1; continue
        if ts in seen: raise ValueError(f'Registro oficial duplicado: {ts}')
        seen.add(ts)
        accepted.append({
            'timestamp_utc': ts, 'site_id': site_id,
            'instrument_id': f'JP_MOE_{station_no}_GLOBE_PLUS_MET',
            'reference_origin': 'measured_instrument',
            'wbgt_reference_c': wbgt, 'latitude_deg': lat, 'longitude_deg': lon,
            'measurement_protocol': 'JP MOE: measured 6-inch globe + JMA air temperature + calculated psychrometric Tw; quality WI=4; NOT ISO natural wet bulb',
            'tg_measured_c': tg, 'tw_calculated_c': tw,
            'quality_code': 4, 'wbgt_class': 1, 'source': API_URL,
            'local_day_jst': ts_to_jst_day(ts),
        })
    accepted.sort(key=lambda r: r['timestamp_utc'])
    counts['accepted'] = len(accepted)
    return accepted, counts


def ts_to_jst_day(timestamp_utc: str) -> str:
    dt = datetime.fromisoformat(timestamp_utc.replace('Z', '+00:00'))
    if dt.tzinfo is None: raise ValueError('UTC obligatorio')
    return dt.astimezone(JST).date().isoformat()


def sha256_json(obj: dict) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def save_raw(path: str | Path, obj: dict) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
