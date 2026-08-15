from __future__ import annotations

import base64
import hashlib
import hmac
import os
from fastapi import Depends, HTTPException, Request


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256": return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError): return False


def require_admin(request: Request):
    raw = request.headers.get("authorization", "")
    if not raw.lower().startswith("basic "): raise HTTPException(401, "Admin authentication required", headers={"WWW-Authenticate":"Basic"})
    try:
        username, password = base64.b64decode(raw.split(" ",1)[1]).decode().split(":",1)
    except Exception: raise HTTPException(401, "Invalid admin credentials", headers={"WWW-Authenticate":"Basic"})
    if not hmac.compare_digest(username, os.getenv("ADMIN_USERNAME", "admin")) or not verify_password(password, os.getenv("ADMIN_PASSWORD_HASH", "")):
        raise HTTPException(401, "Invalid admin credentials", headers={"WWW-Authenticate":"Basic"})
    return username
