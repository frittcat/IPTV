from __future__ import annotations

import hashlib
import json
import os
import re
from urllib.parse import quote

import httpx

from backend.live_master_catalog import match_channel_flexible


class XtreamLiveProvider:
    """Import BR live channels from a user-authorized Xtream-compatible service.

    Credentials are read only from environment variables and are never returned
    by this provider. Upstream URLs remain in the local database behind the
    GaloDoidoTV gateway; they are not written to the repository or public M3U.
    """

    provider_id = "xtream-authorized"

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ):
        self.base_url = (base_url or os.getenv("XTREAM_URL", "")).strip().rstrip("/")
        self.username = username or os.getenv("XTREAM_USERNAME", "")
        self.password = password or os.getenv("XTREAM_PASSWORD", "")

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.username and self.password)

    def _get(self, action: str):
        if not self.configured:
            raise ValueError("Xtream live provider is not configured")
        params = {
            "username": self.username,
            "password": self.password,
            "action": action,
        }
        with httpx.Client(timeout=45, follow_redirects=True, headers={"User-Agent": "GaloDoidoTV/0.3"}) as client:
            return client.get(f"{self.base_url}/player_api.php", params=params).raise_for_status().json()

    @staticmethod
    def _quality(name: str) -> str | None:
        text = (name or "").upper()
        if "4K" in text or "UHD" in text:
            return "2160p"
        if "FHD" in text or "1080" in text:
            return "1080p"
        if re.search(r"\bHD\b", text) or "720" in text:
            return "720p"
        return None

    def discover_br(self) -> list[dict]:
        rows = self._get("get_live_streams")
        result: list[dict] = []
        for item in rows if isinstance(rows, list) else []:
            name = str(item.get("name") or "").strip()
            target = match_channel_flexible(name)
            stream_id = item.get("stream_id")
            if not target or stream_id in (None, ""):
                continue
            extension = str(item.get("container_extension") or "ts").strip().lower()
            if not re.fullmatch(r"[a-z0-9]{1,8}", extension):
                extension = "ts"
            upstream = (
                f"{self.base_url}/live/{quote(self.username, safe='')}/"
                f"{quote(self.password, safe='')}/{stream_id}.{extension}"
            )
            result.append({
                "master": target,
                "provider_name": name,
                "stream_id": str(stream_id),
                "url": upstream,
                "logo": item.get("stream_icon"),
                "epg_channel_id": item.get("epg_channel_id"),
                "quality": self._quality(name),
            })
        return result


def sync_xtream_live(db_execute, now_fn) -> dict:
    provider = XtreamLiveProvider()
    if not provider.configured:
        return {"status": "not_configured", "provider": provider.provider_id, "matched": 0, "streams": 0}

    discovered = provider.discover_br()
    channels_seen: set[str] = set()
    streams = 0
    timestamp = now_fn()

    for item in discovered:
        target = item["master"]
        master_name = target["name"]
        channel_id = "auth-br-" + hashlib.sha1(master_name.encode("utf-8")).hexdigest()[:20]
        channels_seen.add(channel_id)
        aliases = list(dict.fromkeys([master_name, *(target.get("aliases") or []), item["provider_name"]]))
        db_execute(
            "INSERT INTO channels(id,name,country,categories,alt_names,logo,canonical_channel_id,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "name=excluded.name,country=excluded.country,categories=excluded.categories,"
            "alt_names=excluded.alt_names,logo=COALESCE(excluded.logo,channels.logo),"
            "canonical_channel_id=excluded.canonical_channel_id,updated_at=excluded.updated_at",
            (
                channel_id,
                master_name,
                "BR",
                json.dumps([target["category"]], ensure_ascii=False),
                json.dumps(aliases, ensure_ascii=False),
                item.get("logo"),
                f"br:{master_name}",
                timestamp,
            ),
        )
        stream_key = f"{provider.provider_id}|{channel_id}|{item['stream_id']}|{item['url']}"
        stream_db_id = hashlib.sha1(stream_key.encode("utf-8")).hexdigest()
        db_execute(
            "INSERT INTO streams(id,channel_id,feed,title,url,referrer,user_agent,quality,label,source,status,score,last_checked) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "channel_id=excluded.channel_id,title=excluded.title,url=excluded.url,quality=excluded.quality,"
            "source=excluded.source,score=excluded.score",
            (
                stream_db_id,
                channel_id,
                item.get("epg_channel_id"),
                item["provider_name"],
                item["url"],
                None,
                "GaloDoidoTV/0.3",
                item.get("quality"),
                "authorized",
                provider.provider_id,
                "new",
                95.0,
                timestamp,
            ),
        )
        streams += 1

    return {
        "status": "ok",
        "provider": provider.provider_id,
        "matched": len(channels_seen),
        "streams": streams,
    }
