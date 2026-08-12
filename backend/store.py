"""SQLite persistence for the fused analysis bundle.

The bundle (canonical bank/CDR/IPDR records, NCRP complaints, entity registry
and per-file status) is stored as JSON payloads keyed by dataset. Persisting
the bundle means:

  * data survives restarts — no re-ingestion after deploy/reboot,
  * the API can run with several uvicorn workers,
  * `last_ingested` gives operators a cheap freshness check.

The store is intentionally simple (single node, single writer guarded by a
process lock in the API layer). For multi-node deployments keep a shared
volume mounted at APP_DATA_DIR.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bundle (
    key       TEXT PRIMARY KEY,
    payload   TEXT NOT NULL,
    updated   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS investigations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    notes        TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'open',
    created      TEXT NOT NULL,
    updated      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS findings (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    investigation_id INTEGER NOT NULL,
    kind             TEXT NOT NULL,
    title            TEXT NOT NULL,
    detail           TEXT NOT NULL DEFAULT '',
    severity         TEXT NOT NULL DEFAULT 'medium',
    created          TEXT NOT NULL
);
"""

_KEYS = ("bank", "cdr", "ipdr", "subscribers", "complaints", "entities", "files")

_lock = threading.Lock()


def _json_default(o):
    """Bundle entities carry sets (phone/source registries) -> JSON-safe."""
    if isinstance(o, set):
        return sorted(o)
    return str(o)


def _db_path() -> Path:
    return config.data_dir() / "backend.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn


def save_bundle(bundle: dict) -> None:
    """Persist a full bundle atomically (all datasets in one transaction)."""
    with _lock:
        conn = _connect()
        try:
            with conn:
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                for key in _KEYS:
                    conn.execute(
                        "INSERT INTO bundle(key, payload, updated) VALUES(?,?,?)"
                        " ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,"
                        " updated=excluded.updated",
                        (key, json.dumps(bundle.get(key, []),
                                         default=_json_default), now))
        finally:
            conn.close()


def load_bundle() -> dict | None:
    """Return the persisted bundle or None when the store is empty."""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT key, payload FROM bundle").fetchall()
        finally:
            conn.close()
    if not rows:
        return None
    bundle = {k: json.loads(p) for k, p in rows if k in _KEYS}
    bundle["files"] = bundle.get("files", {"ok": [], "skipped": [], "errors": []})
    return bundle


def last_ingested() -> str | None:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT updated FROM bundle WHERE key='bank'").fetchone()
        finally:
            conn.close()
    return row[0] if row else None


def clear_bundle() -> None:
    with _lock:
        conn = _connect()
        try:
            with conn:
                conn.execute("DELETE FROM bundle")
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Investigations (case files with structured findings)
# ---------------------------------------------------------------------------

def create_investigation(title: str, notes: str = "") -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _lock:
        conn = _connect()
        try:
            with conn:
                cur = conn.execute(
                    "INSERT INTO investigations(title, notes, created, updated) "
                    "VALUES(?,?,?,?)", (title, notes, now, now))
                iid = cur.lastrowid
        finally:
            conn.close()
    return {"id": iid, "title": title, "notes": notes, "status": "open",
            "created": now, "updated": now, "findings": []}


def list_investigations() -> list[dict]:
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT id, title, notes, status, created, updated "
                "FROM investigations ORDER BY updated DESC").fetchall()
        finally:
            conn.close()
    out = []
    for r in rows:
        out.append({"id": r[0], "title": r[1], "notes": r[2], "status": r[3],
                    "created": r[4], "updated": r[5]})
    for inv in out:
        inv["findings"] = list_findings(inv["id"])
    return out


def get_investigation(investigation_id: int) -> dict | None:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT id, title, notes, status, created, updated "
                "FROM investigations WHERE id=?", (investigation_id,)).fetchone()
        finally:
            conn.close()
    if not row:
        return None
    inv = {"id": row[0], "title": row[1], "notes": row[2], "status": row[3],
           "created": row[4], "updated": row[5]}
    inv["findings"] = list_findings(inv["id"])
    return inv


def update_investigation(investigation_id: int, title: str | None = None,
                         notes: str | None = None,
                         status: str | None = None) -> dict | None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _lock:
        conn = _connect()
        try:
            with conn:
                fields, vals = [], []
                for col, v in (("title", title), ("notes", notes),
                               ("status", status)):
                    if v is not None:
                        fields.append(f"{col}=?")
                        vals.append(v)
                if not fields:
                    return get_investigation(investigation_id)
                vals.append(now)
                vals.append(investigation_id)
                conn.execute(
                    f"UPDATE investigations SET {', '.join(fields)}, updated=? "
                    f"WHERE id=?", vals)
        finally:
            conn.close()
    return get_investigation(investigation_id)


def delete_investigation(investigation_id: int) -> None:
    with _lock:
        conn = _connect()
        try:
            with conn:
                conn.execute("DELETE FROM findings WHERE investigation_id=?",
                             (investigation_id,))
                conn.execute("DELETE FROM investigations WHERE id=?",
                             (investigation_id,))
        finally:
            conn.close()


def add_finding(investigation_id: int, kind: str, title: str,
                detail: str = "", severity: str = "medium") -> dict | None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _lock:
        conn = _connect()
        try:
            with conn:
                cur = conn.execute(
                    "INSERT INTO findings(investigation_id, kind, title, detail, "
                    "severity, created) VALUES(?,?,?,?,?,?)",
                    (investigation_id, kind, title, detail, severity, now))
                fid = cur.lastrowid
                conn.execute("UPDATE investigations SET updated=? WHERE id=?",
                             (now, investigation_id))
        finally:
            conn.close()
    return {"id": fid, "investigation_id": investigation_id, "kind": kind,
            "title": title, "detail": detail, "severity": severity,
            "created": now}


def list_findings(investigation_id: int) -> list[dict]:
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT id, kind, title, detail, severity, created "
                "FROM findings WHERE investigation_id=? ORDER BY created",
                (investigation_id,)).fetchall()
        finally:
            conn.close()
    return [{"id": r[0], "kind": r[1], "title": r[2], "detail": r[3],
             "severity": r[4], "created": r[5]} for r in rows]
