from __future__ import annotations

import os

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from backend.app import app as app
from backend.auth_runtime import router as auth_router
from backend.client_auth import require_client_session
from backend.content_runtime import router as content_router
from backend.gateway_runtime import router as gateway_router
from backend.media_probe_runtime import router as media_probe_router
from backend.playback_api_runtime import router as playback_api_router
from backend.probed_resolver_runtime import activate as activate_probed_resolver

# GaloDoidoTV is the active product identity. The legacy module/config names
# remain accepted internally during the v0.3 migration so existing installs can
# update in place without losing their database or local configuration.
app.title = "GaloDoidoTV"
app.description = "GaloDoidoTV streaming platform: Live TV, movies, series and device-aware playback."
app.version = "0.3.0-dev"

# Replace only the two legacy byte-proxy routes. Everything else (startup,
# admin middleware, static files, catalog APIs and compatibility endpoints)
# continues to come from backend.app while v0.3 is migrated incrementally.
LEGACY_MEDIA_PATHS = {
    "/live/stream/{channel_id}",
    "/vod/stream/{vod_id}",
}

app.router.routes[:] = [
    route
    for route in app.router.routes
    if getattr(route, "path", None) not in LEGACY_MEDIA_PATHS
]

# Client authentication is feature-gated during the local migration. Keep it
# disabled until at least one client account exists and the Android build with
# login support is installed. Before exposing the service publicly, set
# GALODOIDOTV_REQUIRE_AUTH=true.
CLIENT_AUTH_ENABLED = os.getenv("GALODOIDOTV_REQUIRE_AUTH", "false").strip().lower() in {"1", "true", "yes", "on"}
PUBLIC_CLIENT_PATHS = {
    "/api/v1/auth/login",
}
ADMIN_BASIC_PATHS = {
    "/api/v1/live/sync",
    "/api/v1/vod/sync",
}


@app.middleware("http")
async def protect_client_api(request: Request, call_next):
    if not CLIENT_AUTH_ENABLED or request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    protected = (
        path.startswith("/api/v1/")
        or path.startswith("/live/stream/")
        or path.startswith("/vod/stream/")
    )
    if not protected or path in PUBLIC_CLIENT_PATHS:
        return await call_next(request)

    # Existing admin maintenance endpoints continue to use their own Basic
    # authentication dependency from backend.app.
    authorization = request.headers.get("authorization", "")
    if path in ADMIN_BASIC_PATHS and authorization.lower().startswith("basic "):
        return await call_next(request)

    try:
        require_client_session(request)
    except HTTPException as exc:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers or {})
    return await call_next(request)


# Prefer the new variable name but accept the old one for installed .env files.
public_url = os.getenv("GALODOIDOTV_PUBLIC_URL") or os.getenv("FAMILYSTREAM_PUBLIC_URL", "")
app.state.gateway_public_base = public_url.rstrip("/") or None
activate_probed_resolver()
app.include_router(auth_router)
app.include_router(gateway_router)
app.include_router(playback_api_router)
app.include_router(content_router)
app.include_router(media_probe_router)
