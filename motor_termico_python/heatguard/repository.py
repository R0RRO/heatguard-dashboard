"""Persistencia local sqlite durable, sin secretos ni datos personales por defecto.

No exponer API sin autenticación; para desarrollo, no producción.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path


def _json(value: dict) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def _epoch(timestamp: str) -> float:
    value = datetime.fromisoformat(str(timestamp).replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('timestamp persistido requiere zona horaria')
    return value.timestamp()


def _subject(event: dict) -> tuple[str, str]:
    worker = event.get('context', {}).get('worker_id')
    if isinstance(worker, str) and worker.strip():
        return 'worker_pseudonym', worker.strip()
    return 'device', str(event['device_id'])


class EventRepository:
    def __init__(self, filename: str):
        self.filename = str(filename)
        Path(self.filename).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS telemetry_v4 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                event_key TEXT NOT NULL,
                time_utc TEXT NOT NULL,
                zone_id TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                event_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                time_epoch REAL,
                subject_type TEXT,
                subject_id TEXT,
                UNIQUE(device_id, event_key)
            )''')
            db.execute('CREATE INDEX IF NOT EXISTS ix_hg_device_time ON telemetry_v4(device_id, time_utc)')
            db.execute('''CREATE TABLE IF NOT EXISTS device_events_v31 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                event_key TEXT NOT NULL,
                time_utc TEXT NOT NULL,
                event_type TEXT NOT NULL,
                source TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                time_epoch REAL NOT NULL,
                UNIQUE(device_id,event_key)
            )''')
            db.execute('CREATE INDEX IF NOT EXISTS ix_hg_device_events_time '
                       'ON device_events_v31(device_id,time_epoch)')
            self._migrate(db)

    def _migrate(self, db) -> None:
        """Add v0.30 query columns without discarding existing v0.22 data."""
        columns = {row[1] for row in db.execute('PRAGMA table_info(telemetry_v4)')}
        for name, sql_type in (("time_epoch", "REAL"), ("subject_type", "TEXT"),
                               ("subject_id", "TEXT")):
            if name not in columns:
                db.execute(f'ALTER TABLE telemetry_v4 ADD COLUMN {name} {sql_type}')
        pending = db.execute('''SELECT id,time_utc,event_json FROM telemetry_v4
                                WHERE time_epoch IS NULL OR subject_id IS NULL''').fetchall()
        for row_id, timestamp, payload in pending:
            event = json.loads(payload)
            subject_type, subject_id = _subject(event)
            db.execute('''UPDATE telemetry_v4 SET time_epoch=?,subject_type=?,subject_id=?
                          WHERE id=?''', (_epoch(timestamp), subject_type, subject_id, row_id))
        db.execute('CREATE INDEX IF NOT EXISTS ix_hg_epoch ON telemetry_v4(time_epoch)')
        db.execute('CREATE INDEX IF NOT EXISTS ix_hg_subject_epoch ON telemetry_v4(subject_type,subject_id,time_epoch)')

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.filename, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def event_key(self, event: dict) -> str:
        return str(event.get('event_id') or hashlib.sha256(_json(event).encode()).hexdigest())

    def exists(self, event: dict) -> bool:
        with self._connect() as db:
            row = db.execute('SELECT 1 FROM telemetry_v4 WHERE device_id=? AND event_key=?',
                             (event['device_id'], self.event_key(event))).fetchone()
        return row is not None

    def save(self, event: dict, result: dict) -> bool:
        subject_type, subject_id = _subject(event)
        with self._connect() as db:
            cursor = db.execute('''INSERT OR IGNORE INTO telemetry_v4
             (device_id,event_key,time_utc,zone_id,ingested_at,event_json,result_json,
              time_epoch,subject_type,subject_id)
             VALUES (?,?,?,?,?,?,?,?,?,?)''', (
                event['device_id'], self.event_key(event), event['timestamp'],
                event['context']['zone_id'], datetime.now(timezone.utc).isoformat(),
                _json(event), _json(result),
                _epoch(event['timestamp']), subject_type, subject_id,
            ))
            return cursor.rowcount == 1

    def latest(self, device_id: str | None = None, limit: int = 100) -> list[dict]:
        limit = max(1, min(1000, int(limit)))
        q = 'SELECT event_json,result_json FROM telemetry_v4'
        params = []
        if device_id:
            q += ' WHERE device_id=?'
            params.append(device_id)
        q += ' ORDER BY time_epoch DESC,id DESC LIMIT ?'
        params.append(limit)
        with self._connect() as db:
            rows = db.execute(q, params).fetchall()
        return [{'event': json.loads(a), 'result': json.loads(b)} for a, b in rows]

    def device_ids(self) -> list[str]:
        with self._connect() as db:
            rows = db.execute('SELECT DISTINCT device_id FROM telemetry_v4 ORDER BY device_id').fetchall()
        return [x[0] for x in rows]

    def count(self) -> int:
        with self._connect() as db:
            return db.execute('SELECT COUNT(*) FROM telemetry_v4').fetchone()[0]

    def save_device_event(self, event: dict) -> bool:
        with self._connect() as db:
            cursor = db.execute('''INSERT OR IGNORE INTO device_events_v31
                (device_id,event_key,time_utc,event_type,source,ingested_at,payload_json,time_epoch)
                VALUES (?,?,?,?,?,?,?,?)''', (
                    event['device_id'], str(event['event_id']), event['timestamp'],
                    event['event_type'], event['source'], datetime.now(timezone.utc).isoformat(),
                    _json(event), _epoch(event['timestamp'])
                ))
        return cursor.rowcount == 1

    def device_events(self, device_id: str, *, limit: int = 100,
                      event_type: str | None = None) -> list[dict]:
        limit = max(1, min(1000, int(limit)))
        query = 'SELECT payload_json FROM device_events_v31 WHERE device_id=?'
        params: list[object] = [device_id]
        if event_type:
            query += ' AND event_type=?'; params.append(str(event_type))
        query += ' ORDER BY time_epoch DESC,id DESC LIMIT ?'; params.append(limit)
        with self._connect() as db:
            rows = db.execute(query, params).fetchall()
        return [json.loads(row[0]) for row in rows]

    def device_event_count(self, device_id: str, *, event_type: str | None = None) -> int:
        query = 'SELECT COUNT(*) FROM device_events_v31 WHERE device_id=?'
        params: list[object] = [device_id]
        if event_type:
            query += ' AND event_type=?'; params.append(str(event_type))
        with self._connect() as db:
            return int(db.execute(query, params).fetchone()[0])

    def records_for_restore(self, *, horizon_hours: float = 8.0,
                            limit: int = 250000) -> list[dict]:
        """Return the final horizon relative to the newest stored event.

        Using event time (not process start time) keeps deterministic simulation
        runs reproducible while still restoring a real shift after a restart.
        """
        limit = max(1, min(250000, int(limit)))
        with self._connect() as db:
            newest = db.execute('SELECT MAX(time_epoch) FROM telemetry_v4').fetchone()[0]
            if newest is None:
                return []
            cutoff = float(newest) - float(horizon_hours) * 3600
            rows = db.execute('''SELECT event_json,result_json FROM telemetry_v4
                                 WHERE time_epoch>=? ORDER BY time_epoch ASC,id ASC LIMIT ?''',
                              (cutoff, limit)).fetchall()
        return [{'event': json.loads(a), 'result': json.loads(b)} for a, b in rows]

    def history(self, device_id: str, *, limit: int = 100,
                start_epoch: float | None = None, end_epoch: float | None = None) -> list[dict]:
        limit = max(1, min(10000, int(limit)))
        clauses = ['device_id=?']
        params: list[object] = [device_id]
        if start_epoch is not None:
            clauses.append('time_epoch>=?'); params.append(float(start_epoch))
        if end_epoch is not None:
            clauses.append('time_epoch<=?'); params.append(float(end_epoch))
        params.append(limit)
        with self._connect() as db:
            rows = db.execute(
                'SELECT event_json,result_json FROM telemetry_v4 WHERE '
                + ' AND '.join(clauses) + ' ORDER BY time_epoch DESC,id DESC LIMIT ?', params
            ).fetchall()
        return [{'event': json.loads(a), 'result': json.loads(b)} for a,b in rows]


    def iter_all(self):
        """Itera eventos persistidos; útil para extracción de pares de calibración."""
        with self._connect() as db:
            for event_json, result_json in db.execute(
                'SELECT event_json,result_json FROM telemetry_v4 ORDER BY id ASC'
            ):
                yield {'event': json.loads(event_json), 'result': json.loads(result_json)}
