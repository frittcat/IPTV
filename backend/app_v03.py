from __future__ import annotations

import os

from backend.app import app as app
from backend.gateway_runtime import router as gateway_router
from backend.media_probe_runtime import router as media_probe_router

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

# Optional externally reachable base used when rewriting HLS manifests. When it
# is unset the request's own base URL is used, which is correct for LAN installs.
app.state.gateway_public_base = os.getenv("FAMILYSTREAM_PUBLIC_URL", "").rstrip("/") or None
app.include_router(gateway_router)
app.include_router(media_probe_router)
