"""Almacenamiento de estado EN MEMORIA para demo de telemetría real.

Nunca convierte un indicador exploratorio en autorización de trabajo.
No es base multiusuario ni almacenamiento de producción.
"""
from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from .schema import iso_datetime


class LiveStore:
    def __init__(self, offline_after_s: float = 15):
        self._latest: dict[str, dict] = {}
        self._lock = RLock()
        self.offline_after_s = offline_after_s

    def put(self, event: dict, result: dict) -> dict:
        received_at = datetime.now(timezone.utc).isoformat()
        row = {
            'device_id': event['device_id'],
            'data_type': ('simulated_firmware_fixture' if event.get('transport_metadata', {}).get('simulated')
                          else 'real_device_telemetry'),
            'last_received_at': received_at,
            'sample_timestamp': event['timestamp'],
            'zone_id': result['zone_id'],
            'observations': event['observations'],
            'metrics': result['metrics'],
            'wbgt_outdoor_model': result['wbgt_outdoor_model'],
            'occupational_risk': result['occupational_risk'],
            'limitations': result['limitations'],
        }
        with self._lock:
            self._latest[event['device_id']] = row
        return self._present(row)

    def _present(self, row: dict) -> dict:
        now = datetime.now(timezone.utc)
        age = (now - iso_datetime(row['last_received_at'])).total_seconds()
        return {**row, 'online': 0 <= age <= self.offline_after_s,
                'age_seconds': round(max(0, age), 1),
                'risk_warning': 'No usar el puntaje simulado de React ni presentar WBGT calculado como medición ISO.'}

    def list(self) -> list[dict]:
        with self._lock:
            rows = list(self._latest.values())
        return [self._present(row) for row in rows]

    def get(self, device_id: str) -> dict | None:
        with self._lock:
            row = self._latest.get(device_id)
        return self._present(row) if row else None


live_store = LiveStore()
