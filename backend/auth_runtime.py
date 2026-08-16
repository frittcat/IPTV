from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from backend.client_auth import bearer_token, login, require_client_session, revoke_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    device_id: str = Field(min_length=1, max_length=128)
    device_name: str | None = Field(default=None, max_length=120)


@router.post("/login")
def auth_login(payload: LoginRequest):
    return login(payload.username, payload.password, payload.device_id, payload.device_name)


@router.get("/session")
def auth_session(session: dict = Depends(require_client_session)):
    return {
        "authenticated": True,
        "username": session["username"],
        "device_id": session["device_id"],
        "device_name": session["device_name"],
        "expires_at": session["expires_at"],
        "max_devices": session["max_devices"],
    }


@router.post("/logout")
def auth_logout(request: Request, _session: dict = Depends(require_client_session)):
    revoke_token(bearer_token(request) or "")
    return {"ok": True}
