from __future__ import annotations

import os
from typing import Any, Iterable
import httpx
from .base import VODItem


class XtreamVODProvider:
    provider_id = "xtream_vod"

    def __init__(self, base_url: str | None = None, username: str | None = None, password: str | None = None):
        self.base_url = (base_url or os.getenv("XTREAM_URL", "")).rstrip("/")
        self.username = username or os.getenv("XTREAM_USERNAME", "")
        self.password = password or os.getenv("XTREAM_PASSWORD", "")
        if not all((self.base_url, self.username, self.password)): raise ValueError("Xtream provider requires XTREAM_URL, XTREAM_USERNAME and XTREAM_PASSWORD")

    def _get(self, action: str, **params):
        params.update({"username": self.username, "password": self.password, "action": action})
        return httpx.get(f"{self.base_url}/player_api.php", params=params, timeout=45).raise_for_status().json()

    def categories(self): return ["Movies", "Series", "Seasons", "Episodes"]

    def discover(self, **kwargs) -> Iterable[VODItem]:
        for item in self._get("get_vod_streams") if kwargs.get("movies", True) else []:
            yield VODItem(provider_id=self.provider_id, provider_item_id=str(item.get("stream_id")), item_type="movie", title=item.get("name", "Untitled"), year=int(str(item.get("releaseDate", ""))[:4]) if str(item.get("releaseDate", ""))[:4].isdigit() else None, plot=item.get("plot"), poster=item.get("stream_icon"), stream_url=f"{self.base_url}/movie/{self.username}/{self.password}/{item.get('stream_id')}.{item.get('container_extension','mp4')}", quality=item.get("video", {}).get("width"), rights_status="review_required", metadata=item)
        for item in self._get("get_series") if kwargs.get("series", True) else []:
            yield VODItem(provider_id=self.provider_id, provider_item_id=str(item.get("series_id")), item_type="series", title=item.get("name", "Untitled"), year=int(str(item.get("releaseDate", ""))[:4]) if str(item.get("releaseDate", ""))[:4].isdigit() else None, plot=item.get("plot"), poster=item.get("cover"), rights_status="review_required", metadata=item)

    def sync(self, **kwargs): return self.discover(**kwargs)
    def resolve_stream(self, item): return item.stream_url
    def health_check(self, item): return {"status":"unknown", "url":item.stream_url}
