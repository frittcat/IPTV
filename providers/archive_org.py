from __future__ import annotations

from typing import Iterable
import httpx
from .base import VODItem, rights_status

SEARCH = "https://archive.org/advancedsearch.php"
METADATA = "https://archive.org/metadata/{identifier}"


class ArchiveOrgProvider:
    provider_id = "archive_org"

    def __init__(self, collections: list[str] | None = None, rows: int = 50):
        self.collections = collections or ["feature_films", "opensource_movies"]
        self.rows = min(rows, 200)

    def categories(self) -> list[str]:
        return ["Movies", "Documentaries", "Public Domain"]

    def discover(self, pages: int = 1, **kwargs) -> Iterable[VODItem]:
        with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": "FamilyStream-Hub/0.2"}) as client:
            for collection in self.collections:
                for page in range(1, pages + 1):
                    params = {"q": f"collection:{collection} AND mediatype:movies", "fl[]": ["identifier", "title", "year", "description"], "rows": self.rows, "page": page, "output": "json"}
                    data = client.get(SEARCH, params=params).raise_for_status().json()
                    docs = data.get("response", {}).get("docs", [])
                    if not docs: break
                    for doc in docs:
                        item = self._item(client, doc)
                        if item: yield item

    def sync(self, **kwargs):
        return self.discover(**kwargs)

    def _item(self, client: httpx.Client, doc: dict) -> VODItem | None:
        identifier = doc.get("identifier")
        if not identifier: return None
        meta = client.get(METADATA.format(identifier=identifier)).raise_for_status().json()
        md = meta.get("metadata", {})
        files = meta.get("files", [])
        candidates = [f for f in files if str(f.get("name", "")).lower().endswith((".mp4", ".webm", ".ogv", ".m3u8"))]
        if not candidates: return None
        license_name = md.get("licenseurl") or md.get("rights")
        license_url = md.get("licenseurl")
        rights = rights_status(license_name, md.get("rights"), license_url)
        filename = candidates[0].get("name")
        return VODItem(provider_id=self.provider_id, provider_item_id=identifier, item_type="movie", title=md.get("title") or doc.get("title") or identifier, year=int(str(md.get("year"))[:4]) if str(md.get("year", "")).isdigit() else None, plot=md.get("description"), stream_url=f"https://archive.org/download/{identifier}/{filename}", quality=None, license=license_name, license_url=license_url, creator=md.get("creator"), attribution=md.get("creator"), rights_status=rights, metadata={"collection": md.get("collection"), "format": candidates[0].get("format")})

    def resolve_stream(self, item: VODItem) -> str | None: return item.stream_url
    def health_check(self, item: VODItem) -> dict: return {"status": "unknown", "url": item.stream_url}
