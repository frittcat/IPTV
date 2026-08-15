from __future__ import annotations

import re
from typing import Iterable
import httpx
from .base import VODItem

MOVIE_GROUPS = {"movies", "films", "filmes", "vod", "movie"}
SERIES_GROUPS = {"series", "séries", "tv shows", "shows"}
KIDS_GROUPS = {"kids", "infantil", "children"}
DOC_GROUPS = {"documentaries", "documentary", "documentários"}


def classify(group: str, title: str) -> str:
    text = f"{group} {title}".lower()
    if any(x in text for x in SERIES_GROUPS) or re.search(r"s\d{1,2}e\d{1,2}", text): return "series"
    if any(x in text for x in MOVIE_GROUPS | KIDS_GROUPS | DOC_GROUPS): return "movie"
    if any(x in text for x in ("live", "news", "sport", "radio")): return "live"
    return "unknown"


def parse_m3u(text: str, provider_id: str = "m3u_vod", authorized: bool = False) -> Iterable[VODItem]:
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    current = {}
    for line in lines:
        if line.startswith("#EXTINF"):
            attrs = dict(re.findall(r'(\w[\w-]*)="([^"]*)"', line))
            title = line.split(",", 1)[1].strip() if "," in line else attrs.get("tvg-name", "Untitled")
            current = {"title": title, "group": attrs.get("group-title", ""), "poster": attrs.get("tvg-logo"), "id": attrs.get("tvg-id", title)}
        elif not line.startswith("#") and current:
            kind = classify(current["group"], current["title"])
            if kind in {"movie", "series"}:
                yield VODItem(provider_id=provider_id, provider_item_id=current["id"], item_type=kind, title=current["title"], poster=current["poster"], stream_url=line, rights_status="approved" if authorized else "review_required", metadata={"group": current["group"]})
            current = {}


class M3UVODProvider:
    provider_id = "m3u_vod"
    def __init__(self, url: str, authorized: bool = False): self.url, self.authorized = url, authorized
    def categories(self): return ["Movies", "Series", "Kids", "Documentaries"]
    def discover(self, **kwargs):
        text = httpx.get(self.url, timeout=60, follow_redirects=True).raise_for_status().text
        return parse_m3u(text, self.provider_id, self.authorized)
    def sync(self, **kwargs): return self.discover(**kwargs)
    def resolve_stream(self, item): return item.stream_url
    def health_check(self, item): return {"status":"unknown", "url":item.stream_url}
