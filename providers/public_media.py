from __future__ import annotations

from typing import Iterable
import httpx
from .base import VODItem, rights_status

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
NASA_SEARCH = "https://images-api.nasa.gov/search"
NASA_ASSET = "https://images-api.nasa.gov/asset/{nasa_id}"


class WikimediaProvider:
    provider_id = "wikimedia_commons"

    def categories(self): return ["Documentaries", "Education", "Science", "Culture"]

    def discover(self, search: str = "video", limit: int = 25, **kwargs) -> Iterable[VODItem]:
        params = {"action":"query", "generator":"search", "gsrsearch":search, "gsrnamespace":6, "gsrlimit":min(limit,50), "prop":"imageinfo", "iiprop":"url|mime|mediatype|extmetadata", "iiurlwidth":1280, "format":"json", "formatversion":"2"}
        data = httpx.get(COMMONS_API, params=params, timeout=30, headers={"User-Agent": "FamilyStream-Hub/0.2 (self-hosted; contact via repository)"}).raise_for_status().json()
        for page in data.get("query", {}).get("pages", []):
            info = (page.get("imageinfo") or [{}])[0]
            if info.get("mediatype") != "VIDEO" and not str(info.get("mime", "")).startswith("video/"): continue
            ext = info.get("extmetadata", {})
            def value(key): return (ext.get(key) or {}).get("value")
            license_name, license_url = value("LicenseShortName"), value("LicenseUrl")
            yield VODItem(provider_id=self.provider_id, provider_item_id=str(page.get("pageid")), item_type="movie", title=page.get("title", "").replace("File:", "").rsplit(".",1)[0], plot=value("ImageDescription"), stream_url=info.get("url"), poster=info.get("thumburl"), license=license_name, license_url=license_url, creator=value("Artist"), attribution=value("Credit") or value("Artist"), rights_status=rights_status(license_name, value("UsageTerms"), license_url), metadata={"mime": info.get("mime"), "attribution_required": value("AttributionRequired")})

    def sync(self, **kwargs): return self.discover(**kwargs)
    def categories(self): return ["Documentaries", "Education", "Science", "Culture"]
    def resolve_stream(self, item): return item.stream_url
    def health_check(self, item): return {"status":"unknown", "url":item.stream_url}


class NASAProvider:
    provider_id = "nasa"

    def categories(self): return ["NASA", "Apollo", "Artemis", "ISS", "Mars", "Moon", "Earth", "Space Shuttle", "James Webb", "Hubble", "Documentaries"]

    def discover(self, queries: list[str] | None = None, limit: int = 25, **kwargs) -> Iterable[VODItem]:
        for query in queries or ["Apollo", "Artemis", "ISS", "Mars", "James Webb"]:
            data = httpx.get(NASA_SEARCH, params={"q":query, "media_type":"video", "page_size":min(limit,100)}, timeout=30, headers={"User-Agent":"FamilyStream-Hub/0.2"}).raise_for_status().json()
            for entry in data.get("collection", {}).get("items", []):
                d = {x.get("name"): x.get("value") for x in entry.get("data", [])}
                nasa_id = d.get("nasa_id")
                links = entry.get("links", [])
                preview = next((x.get("href") for x in links if x.get("rel") == "preview"), None)
                if not nasa_id or not preview: continue
                yield VODItem(provider_id=self.provider_id, provider_item_id=nasa_id, item_type="movie", title=d.get("title", nasa_id), year=int(d["date_created"][:4]) if d.get("date_created", "")[:4].isdigit() else None, plot=d.get("description"), stream_url=preview, creator=d.get("center"), attribution="NASA Image and Video Library", rights_status="review_required", metadata={"media_type":d.get("media_type"), "keywords":d.get("keywords",[])})

    def sync(self, **kwargs): return self.discover(**kwargs)
    def resolve_stream(self, item): return item.stream_url
    def health_check(self, item): return {"status":"unknown", "url":item.stream_url}
