"""Authentication (stdlib-only).

Users live in the same SQLite store as the bundle (`users` table).
Passwords are hashed with PBKDF2-HMAC-SHA256 (210k iterations, per-user
salt). Access tokens are short-lived signed JWTs (HMAC-SHA256, no external
JWT library) carrying the username, role and expiry.

Security posture:
  * tokens signed with APP_SECRET — a random 32-byte secret is
    generated and persisted to the data dir on first run if not provided,
    so existing sessions survive restarts,
  * in-memory per-username brute-force throttle (8 failed logins locks the
    account for 5 minutes),
  * register/login are the only public identity endpoints; everything else
    requires a valid Bearer token (see `require_user` dependency).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel

from . import config, store

_PBKDF2_ITERATIONS = 210_000
_TOKEN_TTL_HOURS = config.token_ttl_hours()
_MAX_FAILED = 8
_LOCK_MINUTES = 5

_CSRF: dict[str, list[float]] = {}
_csrf_lock = threading.Lock()


def _secret() -> bytes:
    """Return the signing secret (env first, else a persisted random key)."""
    env = os.environ.get("APP_SECRET")
    if env:
        return env.encode()
    key_file = store._db_path().parent / "auth_secret.key"
    if key_file.exists():
        return key_file.read_bytes()
    key = secrets.token_bytes(32)
    key_file.write_bytes(key)
    config.log.warning(
        "APP_SECRET not set; generated ephemeral signing key at %s "
        "(tokens invalidate if the file is removed)", key_file)
    return key


def _db() -> sqlite3.Connection:
    conn = store._connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username      TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            salt          TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'officer',
            created       TEXT NOT NULL
        )
    """)
    return conn


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ITERATIONS)
    return digest.hex(), salt


def _sign(payload: bytes) -> str:
    return hmac.new(_secret(), payload, hashlib.sha256).hexdigest()


def create_user(username: str, password: str, role: str = "officer") -> dict:
    """Create a user. First user ever becomes admin (bootstrap)."""
    username = (username or "").strip().lower()
    if not username or not password:
        raise HTTPException(400, "username and password are required")
    if len(password) < 8:
        raise HTTPException(400, "password must be at least 8 characters")
    if not username.replace(".", "").replace("_", "").replace("-", "").isalnum():
        raise HTTPException(400, "invalid username (letters, digits, . _ - only)")
    digest, salt = _hash_password(password)
    conn = _db()
    try:
        with conn:
            row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
            if row[0] == 0:
                role = "admin"
            conn.execute(
                "INSERT INTO users(username, password_hash, salt, role, created)"
                " VALUES(?,?,?,?,?)",
                (username, digest, salt, role,
                 datetime.now(timezone.utc).isoformat(timespec="seconds")))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "username already exists")
    finally:
        conn.close()
    return {"username": username, "role": role}


def verify_user(username: str, password: str) -> dict | None:
    username = (username or "").strip().lower()
    conn = _db()
    try:
        row = conn.execute(
            "SELECT username, password_hash, salt, role FROM users"
            " WHERE username=?", (username,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    digest, _ = _hash_password(password, row[2])
    if not hmac.compare_digest(digest, row[1]):
        return None
    return {"username": row[0], "role": row[3]}


def change_password(username: str, current_password: str,
                    new_password: str) -> dict:
    """Verify the current password, then replace it (account tab UX)."""
    username = (username or "").strip().lower()
    if len(new_password) < 8:
        raise HTTPException(400, "password must be at least 8 characters")
    if not verify_user(username, current_password):
        raise HTTPException(403, "current password is incorrect")
    digest, salt = _hash_password(new_password)
    conn = _db()
    try:
        with conn:
            cur = conn.execute(
                "UPDATE users SET password_hash=?, salt=? WHERE username=?",
                (digest, salt, username))
            if cur.rowcount == 0:
                raise HTTPException(404, "user not found")
    finally:
        conn.close()
    return {"username": username, "detail": "password updated"}


def _throttle(username: str, record: bool) -> bool:
    """Return True when the account is locked out (rate-limit guard)."""
    with _csrf_lock:
        now = time.monotonic()
        failures = [t for t in _CSRF.get(username, []) if now - t < 300]
        if record:
            failures.append(now)
        _CSRF[username] = failures
        return len(failures) >= _MAX_FAILED


def issue_token(username: str, role: str) -> str:
    exp = int((datetime.now(timezone.utc)
               + timedelta(hours=_TOKEN_TTL_HOURS)).timestamp())
    header = {"alg": "HS256", "typ": "JWT"}
    body = {"sub": username, "role": role, "exp": exp}
    def b64(d: dict) -> str:
        raw = json.dumps(d, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    payload = f"{b64(header)}.{b64(body)}".encode()
    return f"{payload.decode()}.{_sign(payload)}"


def decode_token(token: str) -> dict:
    """Validate a token; raise 401 on any tampering/expiry."""
    try:
        head, body, sig = token.split(".")
        payload = f"{head}.{body}".encode()
        expected = _sign(payload)
        if not hmac.compare_digest(expected, sig):
            raise ValueError("bad signature")
        info = json.loads(base64.urlsafe_b64decode(
            body + "=" * (-len(body) % 4)))
        if int(info.get("exp", 0)) < int(time.time()):
            raise ValueError("expired")
        return {"username": info["sub"], "role": info["role"]}
    except Exception:
        raise HTTPException(401, "invalid or expired token",
                            headers={"WWW-Authenticate": "Bearer"})


def require_user(authorization: str | None = Header(default=None)) -> dict:
    """FastAPI dependency guarding every protected endpoint."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "authentication required",
                            headers={"WWW-Authenticate": "Bearer"})
    return decode_token(authorization.split(" ", 1)[1].strip())


def require_admin(user: dict = Depends(require_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(403, "admin role required")
    return user


class RegisterBody(BaseModel):
    username: str
    password: str


class LoginBody(BaseModel):
    username: str
    password: str


def register(body: RegisterBody) -> dict:
    if not config.allow_signup():
        raise HTTPException(403, "public sign-up is disabled on this server")
    return create_user(body.username, body.password)


def login(body: LoginBody) -> dict:
    username = body.username.strip().lower()
    if _throttle(username, record=False):
        raise HTTPException(429, "too many failed attempts; try again later")
    user = verify_user(username, body.password)
    if not user:
        _throttle(username, record=True)
        raise HTTPException(401, "invalid username or password")
    return {
        "access_token": issue_token(user["username"], user["role"]),
        "token_type": "bearer",
        "user": {"username": user["username"], "role": user["role"]},
    }
