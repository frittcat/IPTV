from __future__ import annotations

import os

from backend.app import app as app
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

# Prefer the new variable name but accept the old one for installed .env files.
public_url = os.getenv("GALODOIDOTV_PUBLIC_URL") or os.getenv("FAMILYSTREAM_PUBLIC_URL", "")
app.state.gateway_public_base = public_url.rstrip("/") or None
activate_probed_resolver()
app.include_router(gateway_router)
app.include_router(playback_api_router)
app.include_router(content_router)
app.include_router(media_probe_router)
