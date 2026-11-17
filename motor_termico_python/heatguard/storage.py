"""Persistencia SQLite local de eventos originales + resultados derivados.

Solo para desarrollo. No incluye control de acceso, anonimización ni retención.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from contextlib import closing


def save_record(db_path: str, event: dict, result: dict) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as con, con:
        con.execute("""
          CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            event_timestamp TEXT NOT NULL,
            zone_id TEXT NOT NULL,
            ingested_at_utc TEXT NOT NULL,
            event_json TEXT NOT NULL,
            result_json TEXT NOT NULL
          )
        """)
        con.execute("""INSERT INTO events (device_id, event_timestamp, zone_id,
                       ingested_at_utc, event_json, result_json) VALUES (?, ?, ?, ?, ?, ?)""", (
            event["device_id"], event["timestamp"], event["context"]["zone_id"],
            datetime.now(timezone.utc).isoformat(),
            json.dumps(event, ensure_ascii=False), json.dumps(result, ensure_ascii=False),
        ))


def latest_records(db_path: str, limit: int = 10) -> list[dict]:
    if limit < 1 or limit > 1000:
        raise ValueError("limit debe estar entre 1 y 1000.")
    with closing(sqlite3.connect(db_path)) as con:
        rows = con.execute(
            "SELECT event_json, result_json FROM events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [{"event": json.loads(a), "result": json.loads(b)} for a, b in rows]
