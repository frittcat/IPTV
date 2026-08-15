from __future__ import annotations

import os
import httpx


class DispatcharrClient:
    def __init__(self, base_url: str | None = None, username: str | None = None, password: str | None = None):
        self.base_url = (base_url or os.getenv("DISPATCHARR_URL", "http://dispatcharr:9191")).rstrip("/")
        self.auth = (username or os.getenv("DISPATCHARR_USERNAME", ""), password or os.getenv("DISPATCHARR_PASSWORD", ""))

    def swagger(self) -> dict:
        candidates = ["/swagger.json", "/api/schema/", "/openapi.json"]
        with httpx.Client(timeout=10, follow_redirects=True, auth=self.auth if all(self.auth) else None) as client:
            for path in candidates:
                try:
                    response = client.get(self.base_url + path)
                    if response.status_code == 200 and response.headers.get("content-type", "").startswith("application/json"):
                        return response.json()
                except httpx.HTTPError:
                    continue
        return {}

    def status(self) -> dict:
        schema = self.swagger()
        paths = sorted(schema.get("paths", {}))
        return {"reachable": bool(schema), "base_url": self.base_url, "openapi_paths": paths, "manual_configuration_required": not bool(schema)}

    def integration_plan(self) -> dict:
        return {"m3u": "/family-tv.m3u", "xmltv": "/family-tv.xml", "stable_live_proxy": "/live/stream/{channel_id}", "note": "Dispatcharr Swagger is runtime-discovered; use its current API schema before mutating provider/channel objects."}
