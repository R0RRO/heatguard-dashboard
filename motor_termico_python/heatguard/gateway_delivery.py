"""Entrega HTTP autenticada y durable para pasarelas HeatGuard.

El outbox hace que una caída de red o del backend no descarte silenciosamente
un evento. La API conserva su propia deduplicación; por eso es seguro reenviar
si el proceso cae después del POST pero antes de marcar la fila como enviada.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class GatewayDeliveryError(RuntimeError):
    """Fallo transitorio de red o servidor."""


class GatewayAuthError(GatewayDeliveryError):
    """La clave falta o no tiene permiso; no se reintenta en bucle rápido."""


class GatewayRejectedError(GatewayDeliveryError):
    """La API rechazó permanentemente la forma o contenido del evento."""


def configured_gateway_api_key() -> str | None:
    """Obtiene una clave solo desde el entorno, nunca desde el código."""
    import os
    return (os.environ.get("HG_GATEWAY_API_KEY") or
            os.environ.get("HG_ADMIN_API_KEY") or
            os.environ.get("HG_API_KEY"))


def _canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def delivery_key(endpoint: str, payload: dict) -> str:
    explicit = payload.get("event_id")
    identity = f"{payload.get('device_id', '')}:{explicit}" if explicit else _canonical(payload)
    return hashlib.sha256(f"{endpoint}\n{identity}".encode("utf-8")).hexdigest()


class HttpJsonTransport:
    def __init__(self, *, api_key: str | None = None, timeout_s: float = 8.0):
        self.api_key = api_key
        self.timeout_s = float(timeout_s)

    def post(self, url: str, payload: dict) -> dict:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        request = Request(url, data=_canonical(payload).encode("utf-8"),
                          headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.timeout_s) as response:
                body = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            if exc.code in (401, 403):
                raise GatewayAuthError(f"API rechazó autenticación HTTP {exc.code}: {detail}") from exc
            if 400 <= exc.code < 500 and exc.code != 429:
                raise GatewayRejectedError(f"API rechazó evento HTTP {exc.code}: {detail}") from exc
            raise GatewayDeliveryError(f"API no disponible HTTP {exc.code}: {detail}") from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise GatewayDeliveryError(f"Fallo de red al entregar evento: {exc}") from exc
        try:
            return json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            raise GatewayDeliveryError("La API respondió 2xx con JSON inválido") from exc


class DurableOutbox:
    def __init__(self, filename: str):
        self.filename = str(filename)
        Path(self.filename).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS gateway_outbox_v31 (
                delivery_key TEXT PRIMARY KEY,
                endpoint TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt_epoch REAL NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at TEXT NOT NULL,
                sent_at TEXT
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS ix_hg_outbox_ready "
                       "ON gateway_outbox_v31(status,next_attempt_epoch)")
            db.execute("""CREATE TABLE IF NOT EXISTS gateway_device_state_v31 (
                device_id TEXT PRIMARY KEY,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.filename, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def enqueue(self, endpoint: str, payload: dict) -> tuple[str, bool]:
        key = delivery_key(endpoint, payload)
        with self._connect() as db:
            cursor = db.execute("""INSERT OR IGNORE INTO gateway_outbox_v31
                (delivery_key,endpoint,payload_json,created_at)
                VALUES (?,?,?,?)""", (
                    key, endpoint, _canonical(payload), datetime.now(timezone.utc).isoformat()
                ))
        return key, cursor.rowcount == 1

    def ready(self, *, now_epoch: float | None = None, limit: int = 25) -> list[dict]:
        now_epoch = time.time() if now_epoch is None else float(now_epoch)
        with self._connect() as db:
            rows = db.execute("""SELECT delivery_key,endpoint,payload_json,attempts
                FROM gateway_outbox_v31
                WHERE status='pending' AND next_attempt_epoch<=?
                ORDER BY created_at ASC LIMIT ?""", (now_epoch, max(1, min(500, limit)))).fetchall()
        return [{"key": k, "endpoint": e, "payload": json.loads(p), "attempts": a}
                for k, e, p, a in rows]

    def mark_sent(self, key: str) -> None:
        with self._connect() as db:
            db.execute("""UPDATE gateway_outbox_v31 SET status='sent',sent_at=?,last_error=NULL
                          WHERE delivery_key=?""",
                       (datetime.now(timezone.utc).isoformat(), key))

    def mark_failure(self, key: str, error: str, *, delay_s: float,
                     permanent: bool = False) -> None:
        with self._connect() as db:
            db.execute("""UPDATE gateway_outbox_v31
                          SET status=?,attempts=attempts+1,next_attempt_epoch=?,last_error=?
                          WHERE delivery_key=?""",
                       ("rejected" if permanent else "pending", time.time() + delay_s,
                        str(error)[:2000], key))

    def stats(self) -> dict[str, int]:
        with self._connect() as db:
            rows = db.execute("SELECT status,COUNT(*) FROM gateway_outbox_v31 GROUP BY status").fetchall()
        counts = {"pending": 0, "sent": 0, "rejected": 0}
        counts.update({str(k): int(v) for k, v in rows})
        return counts

    def load_device_state(self, device_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT state_json FROM gateway_device_state_v31 WHERE device_id=?",
                             (str(device_id),)).fetchone()
        return json.loads(row[0]) if row else None

    def save_device_state(self, device_id: str, state: dict) -> None:
        with self._connect() as db:
            db.execute("""INSERT INTO gateway_device_state_v31(device_id,state_json,updated_at)
                          VALUES (?,?,?)
                          ON CONFLICT(device_id) DO UPDATE SET
                          state_json=excluded.state_json,updated_at=excluded.updated_at""",
                       (str(device_id), _canonical(state),
                        datetime.now(timezone.utc).isoformat()))


class GatewayDelivery:
    def __init__(self, outbox_path: str, *, api_key: str | None = None,
                 timeout_s: float = 8.0, base_backoff_s: float = 1.0,
                 max_backoff_s: float = 60.0):
        self.outbox = DurableOutbox(outbox_path)
        self.transport = HttpJsonTransport(api_key=api_key, timeout_s=timeout_s)
        self.base_backoff_s = max(0.1, float(base_backoff_s))
        self.max_backoff_s = max(self.base_backoff_s, float(max_backoff_s))

    def enqueue(self, endpoint: str, payload: dict) -> tuple[str, bool]:
        return self.outbox.enqueue(endpoint, payload)

    def deliver_ready(self, *, limit: int = 25) -> dict:
        delivered = rejected = failed = 0
        errors: list[str] = []
        for item in self.outbox.ready(limit=limit):
            try:
                self.transport.post(item["endpoint"], item["payload"])
            except GatewayRejectedError as exc:
                self.outbox.mark_failure(item["key"], str(exc), delay_s=0, permanent=True)
                rejected += 1; errors.append(str(exc))
            except GatewayAuthError as exc:
                # Mantener el evento: el operador puede corregir la variable y reiniciar.
                self.outbox.mark_failure(item["key"], str(exc), delay_s=self.max_backoff_s)
                failed += 1; errors.append(str(exc))
            except GatewayDeliveryError as exc:
                delay = min(self.max_backoff_s,
                            self.base_backoff_s * (2 ** min(10, item["attempts"])))
                self.outbox.mark_failure(item["key"], str(exc), delay_s=delay)
                failed += 1; errors.append(str(exc))
            else:
                self.outbox.mark_sent(item["key"])
                delivered += 1
        return {"delivered": delivered, "failed": failed, "rejected": rejected,
                "errors": errors, "outbox": self.outbox.stats()}
