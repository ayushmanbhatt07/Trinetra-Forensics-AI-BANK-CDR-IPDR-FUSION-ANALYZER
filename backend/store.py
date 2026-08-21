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
    username  TEXT NOT NULL,
    key       TEXT NOT NULL,
    payload   TEXT NOT NULL,
    updated   TEXT NOT NULL,
    PRIMARY KEY (username, key)
);
CREATE TABLE IF NOT EXISTS investigations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT NOT NULL,
    title        TEXT NOT NULL,
    notes        TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'open',
    created      TEXT NOT NULL,
    updated      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS findings (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    username         TEXT NOT NULL,
    investigation_id INTEGER NOT NULL,
    kind             TEXT NOT NULL,
    title            TEXT NOT NULL,
    detail           TEXT NOT NULL DEFAULT '',
    severity         TEXT NOT NULL DEFAULT 'medium',
    created          TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pipeline_jobs (
    job_id           TEXT PRIMARY KEY,
    username         TEXT NOT NULL,
    dataset_id       TEXT NOT NULL,
    status           TEXT NOT NULL,
    stage            TEXT NOT NULL,
    progress         INTEGER,
    started_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    completed_at     TEXT,
    error_message    TEXT,
    fused_ready      INTEGER NOT NULL DEFAULT 0,
    anomalies_ready  INTEGER NOT NULL DEFAULT 0,
    graphs_ready     INTEGER NOT NULL DEFAULT 0
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


def _migrate_legacy_db(conn: sqlite3.Connection):
    """Migrate legacy single-tenant tables to multi-tenant by assigning old data to 'admin'."""
    # Check if investigations exists before renaming to handle partial states safely
    tables = [col[0] for col in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    
    if "bundle" in tables:
        conn.execute("ALTER TABLE bundle RENAME TO legacy_bundle;")
    if "investigations" in tables:
        conn.execute("ALTER TABLE investigations RENAME TO legacy_investigations;")
    if "findings" in tables:
        conn.execute("ALTER TABLE findings RENAME TO legacy_findings;")
    if "pipeline_jobs" in tables:
        conn.execute("ALTER TABLE pipeline_jobs RENAME TO legacy_pipeline_jobs;")
        
    conn.executescript(_SCHEMA)
    
    if "bundle" in tables:
        conn.execute("INSERT INTO bundle(username, key, payload, updated) SELECT 'admin', key, payload, updated FROM legacy_bundle;")
        conn.execute("DROP TABLE legacy_bundle;")
    if "investigations" in tables:
        conn.execute("INSERT INTO investigations(id, username, title, notes, status, created, updated) SELECT id, 'admin', title, notes, status, created, updated FROM legacy_investigations;")
        conn.execute("DROP TABLE legacy_investigations;")
    if "findings" in tables:
        conn.execute("INSERT INTO findings(id, username, investigation_id, kind, title, detail, severity, created) SELECT id, 'admin', investigation_id, kind, title, detail, severity, created FROM legacy_findings;")
        conn.execute("DROP TABLE legacy_findings;")
    if "pipeline_jobs" in tables:
        conn.execute("INSERT INTO pipeline_jobs(job_id, username, dataset_id, status, stage, progress, started_at, updated_at, completed_at, error_message, fused_ready, anomalies_ready, graphs_ready) SELECT job_id, 'admin', dataset_id, status, stage, progress, started_at, updated_at, completed_at, error_message, fused_ready, anomalies_ready, graphs_ready FROM legacy_pipeline_jobs;")
        conn.execute("DROP TABLE legacy_pipeline_jobs;")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(bundle)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if columns and "username" not in columns:
        _migrate_legacy_db(conn)
    else:
        conn.executescript(_SCHEMA)
        
    return conn


def save_bundle(bundle: dict, username: str) -> None:
    """Persist a full bundle atomically (all datasets in one transaction) for a user."""
    with _lock:
        conn = _connect()
        try:
            with conn:
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                for key in _KEYS:
                    conn.execute(
                        "INSERT INTO bundle(username, key, payload, updated) VALUES(?,?,?,?)"
                        " ON CONFLICT(username, key) DO UPDATE SET payload=excluded.payload,"
                        " updated=excluded.updated",
                        (username, key, json.dumps(bundle.get(key, []),
                                         default=_json_default), now))
        finally:
            conn.close()


def load_bundle(username: str) -> dict | None:
    """Return the persisted bundle for a user or None when the store is empty."""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT key, payload FROM bundle WHERE username=?", (username,)).fetchall()
        finally:
            conn.close()
    if not rows:
        return None
    out = {}
    for k, p in rows:
        out[k] = json.loads(p)
    if "entities" in out:
        for ek in ("phones", "accounts", "upi_ids", "imeis", "imsis", "ips", "names"):
            if ek in out["entities"]:
                out["entities"][ek] = set(out["entities"][ek])
    return out


def load_richest_bundle() -> tuple[str | None, dict | None]:
    """Find the bundle across all users that contains the most forensic data."""
    with _lock:
        conn = _connect()
        try:
            users = [r[0] for r in conn.execute("SELECT DISTINCT username FROM bundle").fetchall()]
        finally:
            conn.close()
    best_user = None
    best_bundle = None
    best_count = 0
    for u in users:
        b = load_bundle(u)
        if b:
            cnt = len(b.get("bank", [])) + len(b.get("cdr", [])) + len(b.get("ipdr", []))
            if cnt > best_count:
                best_count = cnt
                best_user = u
                best_bundle = b
    return best_user, best_bundle


def clear_bundle(username: str) -> None:
    """Drop all persisted bundle tables and pipeline jobs from SQLite for a user."""
    with _lock:
        conn = _connect()
        try:
            with conn:
                conn.execute("DELETE FROM bundle WHERE username=?", (username,))
                conn.execute("DELETE FROM pipeline_jobs WHERE username=?", (username,))
                conn.execute("DELETE FROM findings WHERE username=?", (username,))
                conn.execute("DELETE FROM investigations WHERE username=?", (username,))
        finally:
            conn.close()


def save_pipeline_job(job: dict, username: str) -> None:
    """Upsert a pipeline job into the database for a user."""
    with _lock:
        conn = _connect()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO pipeline_jobs(job_id, username, dataset_id, status, stage, progress, started_at, updated_at, completed_at, error_message, fused_ready, anomalies_ready, graphs_ready) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(job_id) DO UPDATE SET "
                    "status=excluded.status, stage=excluded.stage, progress=excluded.progress, updated_at=excluded.updated_at, "
                    "completed_at=excluded.completed_at, error_message=excluded.error_message, "
                    "fused_ready=excluded.fused_ready, anomalies_ready=excluded.anomalies_ready, graphs_ready=excluded.graphs_ready",
                    (
                        job["job_id"], username, job["dataset_id"], job["status"], job["stage"], job.get("progress"),
                        job["started_at"], job["updated_at"], job.get("completed_at"), job.get("error_message"),
                        1 if job.get("fused_ready") else 0,
                        1 if job.get("anomalies_ready") else 0,
                        1 if job.get("graphs_ready") else 0
                    )
                )
        finally:
            conn.close()


def get_active_pipeline_job(username: str) -> dict | None:
    """Get the most recently updated active pipeline job for a user, if any."""
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT job_id, dataset_id, status, stage, progress, started_at, updated_at, completed_at, error_message, fused_ready, anomalies_ready, graphs_ready "
                "FROM pipeline_jobs WHERE username=? ORDER BY updated_at DESC LIMIT 1", (username,)
            ).fetchone()
        finally:
            conn.close()
            
    if not row:
        return None
        
    return {
        "job_id": row[0],
        "dataset_id": row[1],
        "status": row[2],
        "stage": row[3],
        "progress": row[4],
        "started_at": row[5],
        "updated_at": row[6],
        "completed_at": row[7],
        "error_message": row[8],
        "fused_ready": bool(row[9]),
        "anomalies_ready": bool(row[10]),
        "graphs_ready": bool(row[11])
    }


def last_ingested(username: str) -> str | None:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT updated FROM bundle WHERE key='bank' AND username=?", (username,)).fetchone()
        finally:
            conn.close()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Investigations (case files with structured findings)
# ---------------------------------------------------------------------------

def create_investigation(title: str, username: str, notes: str = "") -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _lock:
        conn = _connect()
        try:
            with conn:
                cur = conn.execute(
                    "INSERT INTO investigations(username, title, notes, created, updated) "
                    "VALUES(?,?,?,?,?)", (username, title, notes, now, now))
                iid = cur.lastrowid
        finally:
            conn.close()
    return {"id": iid, "title": title, "notes": notes, "status": "open",
            "created": now, "updated": now, "findings": []}


def list_investigations(username: str) -> list[dict]:
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT id, title, notes, status, created, updated "
                "FROM investigations WHERE username=? ORDER BY updated DESC", (username,)).fetchall()
        finally:
            conn.close()
    out = []
    for r in rows:
        out.append({"id": r[0], "title": r[1], "notes": r[2], "status": r[3],
                    "created": r[4], "updated": r[5]})
    for inv in out:
        inv["findings"] = list_findings(inv["id"], username)
    return out


def get_investigation(investigation_id: int, username: str) -> dict | None:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT id, title, notes, status, created, updated "
                "FROM investigations WHERE id=? AND username=?", (investigation_id, username)).fetchone()
        finally:
            conn.close()
    if not row:
        return None
    inv = {"id": row[0], "title": row[1], "notes": row[2], "status": row[3],
           "created": row[4], "updated": row[5]}
    inv["findings"] = list_findings(inv["id"], username)
    return inv


def update_investigation(investigation_id: int, username: str, title: str | None = None,
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
                    return get_investigation(investigation_id, username)
                vals.append(now)
                vals.append(investigation_id)
                vals.append(username)
                conn.execute(
                    f"UPDATE investigations SET {', '.join(fields)}, updated=? "
                    f"WHERE id=? AND username=?", vals)
        finally:
            conn.close()
    return get_investigation(investigation_id, username)


def delete_investigation(investigation_id: int, username: str) -> None:
    with _lock:
        conn = _connect()
        try:
            with conn:
                # First delete associated findings to avoid orphans
                conn.execute("DELETE FROM findings WHERE investigation_id=? AND username=?",
                             (investigation_id, username))
                conn.execute("DELETE FROM investigations WHERE id=? AND username=?",
                             (investigation_id, username))
        finally:
            conn.close()


def add_finding(investigation_id: int, username: str, kind: str, title: str,
                detail: str = "", severity: str = "medium") -> dict | None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _lock:
        conn = _connect()
        try:
            with conn:
                # Verify investigation ownership before adding finding
                row = conn.execute("SELECT id FROM investigations WHERE id=? AND username=?", (investigation_id, username)).fetchone()
                if not row:
                    return None
                    
                cur = conn.execute(
                    "INSERT INTO findings(username, investigation_id, kind, title, detail, "
                    "severity, created) VALUES(?,?,?,?,?,?,?)",
                    (username, investigation_id, kind, title, detail, severity, now))
                fid = cur.lastrowid
                conn.execute("UPDATE investigations SET updated=? WHERE id=? AND username=?",
                             (now, investigation_id, username))
        finally:
            conn.close()
    return {"id": fid, "investigation_id": investigation_id, "kind": kind,
            "title": title, "detail": detail, "severity": severity,
            "created": now}


def list_findings(investigation_id: int, username: str) -> list[dict]:
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT id, kind, title, detail, severity, created "
                "FROM findings WHERE investigation_id=? AND username=? ORDER BY created",
                (investigation_id, username)).fetchall()
        finally:
            conn.close()
    return [{"id": r[0], "kind": r[1], "title": r[2], "detail": r[3],
             "severity": r[4], "created": r[5]} for r in rows]
