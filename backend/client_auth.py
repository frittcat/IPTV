from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,64}$")
PBKDF2_ITERATIONS = int(os.getenv("GALODOIDOTV_PBKDF2_ITERATIONS", "310000"))
SESSION_DAYS = int(os.getenv("GALODOIDOTV_SESSION_DAYS", "180"))


def _db_execute(sql: str, params: tuple = (), fetch: bool = False):
    from backend.app import db_execute

    return db_execute(sql, params, fetch)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must contain at least 8 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, expected_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        ).hex()
        return hmac.compare_digest(actual, expected_hex)
    except (TypeError, ValueError):
        return False


def normalize_username(username: str) -> str:
    value = username.strip().lower()
    if not USERNAME_RE.fullmatch(value):
        raise ValueError("Username must be 3-64 characters using letters, numbers, dot, dash or underscore")
    return value


def create_user(username: str, password: str, max_devices: int = 3) -> str:
    username = normalize_username(username)
    if max_devices < 1 or max_devices > 50:
        raise ValueError("max_devices must be between 1 and 50")
    user_id = uuid.uuid4().hex
    timestamp = _iso(_utcnow())
    try:
        _db_execute(
            "INSERT INTO app_users(id,username,password_hash,active,max_devices,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (user_id, username, hash_password(password), 1, max_devices, timestamp, timestamp),
        )
    except Exception as exc:
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise ValueError(f"User already exists: {username}") from exc
        raise
    return user_id


def set_password(username: str, password: str) -> None:
    username = normalize_username(username)
    rows = _db_execute("SELECT id FROM app_users WHERE username=?", (username,), True)
    if not rows:
        raise ValueError(f"Unknown user: {username}")
    _db_execute(
        "UPDATE app_users SET password_hash=?, updated_at=? WHERE username=?",
        (hash_password(password), _iso(_utcnow()), username),
    )
    _db_execute("UPDATE app_sessions SET revoked=1 WHERE user_id=?", (rows[0][0],))


def set_active(username: str, active: bool) -> None:
    username = normalize_username(username)
    rows = _db_execute("SELECT id FROM app_users WHERE username=?", (username,), True)
    if not rows:
        raise ValueError(f"Unknown user: {username}")
    user_id = rows[0][0]
    _db_execute(
        "UPDATE app_users SET active=?, updated_at=? WHERE id=?",
        (1 if active else 0, _iso(_utcnow()), user_id),
    )
    if not active:
        _db_execute("UPDATE app_sessions SET revoked=1 WHERE user_id=?", (user_id,))


def set_max_devices(username: str, max_devices: int) -> None:
    username = normalize_username(username)
    if max_devices < 1 or max_devices > 50:
        raise ValueError("max_devices must be between 1 and 50")
    rows = _db_execute("SELECT id FROM app_users WHERE username=?", (username,), True)
    if not rows:
        raise ValueError(f"Unknown user: {username}")
    _db_execute(
        "UPDATE app_users SET max_devices=?, updated_at=? WHERE username=?",
        (max_devices, _iso(_utcnow()), username),
    )


def list_users() -> list[dict]:
    rows = _db_execute(
        "SELECT id,username,active,max_devices,created_at,updated_at FROM app_users ORDER BY username",
        fetch=True,
    )
    return [
        {
            "id": row[0],
            "username": row[1],
            "active": bool(row[2]),
            "max_devices": row[3],
            "created_at": row[4],
            "updated_at": row[5],
        }
        for row in rows
    ]


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _prune_expired_sessions(user_id: str | None = None) -> None:
    cutoff = _iso(_utcnow())
    if user_id:
        _db_execute(
            "UPDATE app_sessions SET revoked=1 WHERE user_id=? AND revoked=0 AND expires_at<=?",
            (user_id, cutoff),
        )
    else:
        _db_execute("UPDATE app_sessions SET revoked=1 WHERE revoked=0 AND expires_at<=?", (cutoff,))


def login(username: str, password: str, device_id: str, device_name: str | None = None) -> dict:
    username = normalize_username(username)
    device_id = device_id.strip()
    if not device_id or len(device_id) > 128:
        raise HTTPException(400, "Invalid device id")

    rows = _db_execute(
        "SELECT id,username,password_hash,active,max_devices FROM app_users WHERE username=?",
        (username,),
        True,
    )
    if not rows:
        raise HTTPException(401, "Invalid username or password")

    user_id, stored_username, password_hash, active, max_devices = rows[0]
    if not active or not verify_password(password, password_hash):
        raise HTTPException(401, "Invalid username or password")

    _prune_expired_sessions(user_id)
    # A fresh login on the same physical device replaces its previous session.
    _db_execute(
        "UPDATE app_sessions SET revoked=1 WHERE user_id=? AND device_id=? AND revoked=0",
        (user_id, device_id),
    )
    active_rows = _db_execute(
        "SELECT DISTINCT device_id FROM app_sessions WHERE user_id=? AND revoked=0",
        (user_id,),
        True,
    )
    if len(active_rows) >= int(max_devices):
        raise HTTPException(403, "Device limit reached for this account")

    raw_token = secrets.token_urlsafe(48)
    timestamp = _utcnow()
    expires = timestamp + timedelta(days=SESSION_DAYS)
    session_id = uuid.uuid4().hex
    _db_execute(
        "INSERT INTO app_sessions(id,user_id,token_hash,device_id,device_name,created_at,last_seen,expires_at,revoked) VALUES(?,?,?,?,?,?,?,?,?)",
        (
            session_id,
            user_id,
            _token_hash(raw_token),
            device_id,
            (device_name or "").strip()[:120] or None,
            _iso(timestamp),
            _iso(timestamp),
            _iso(expires),
            0,
        ),
    )
    return {
        "token": raw_token,
        "token_type": "Bearer",
        "username": stored_username,
        "expires_at": _iso(expires),
        "max_devices": int(max_devices),
    }


def session_from_token(token: str, *, touch: bool = True) -> dict | None:
    if not token:
        return None
    rows = _db_execute(
        "SELECT s.id,s.user_id,s.device_id,s.device_name,s.expires_at,s.revoked,u.username,u.active,u.max_devices "
        "FROM app_sessions s JOIN app_users u ON u.id=s.user_id WHERE s.token_hash=?",
        (_token_hash(token),),
        True,
    )
    if not rows:
        return None
    session_id, user_id, device_id, device_name, expires_at, revoked, username, active, max_devices = rows[0]
    try:
        expires = datetime.fromisoformat(expires_at)
    except ValueError:
        return None
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if revoked or not active or expires <= _utcnow():
        return None

    if touch:
        now = _utcnow()
        new_expiry = now + timedelta(days=SESSION_DAYS)
        _db_execute(
            "UPDATE app_sessions SET last_seen=?, expires_at=? WHERE id=?",
            (_iso(now), _iso(new_expiry), session_id),
        )
        expires_at = _iso(new_expiry)

    return {
        "session_id": session_id,
        "user_id": user_id,
        "username": username,
        "device_id": device_id,
        "device_name": device_name,
        "expires_at": expires_at,
        "max_devices": int(max_devices),
    }


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    return header.split(" ", 1)[1].strip() or None


def require_client_session(request: Request) -> dict:
    session = session_from_token(bearer_token(request) or "")
    if session is None:
        raise HTTPException(401, "Valid GaloDoidoTV session required")
    return session


def revoke_token(token: str) -> None:
    if token:
        _db_execute("UPDATE app_sessions SET revoked=1 WHERE token_hash=?", (_token_hash(token),))
