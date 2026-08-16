from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import httpx

from backend.app import (
    API_URLS,
    FREE_TV_URL,
    MIN_SCORE,
    canonical,
    db_connect,
    export_files,
    init_db,
    norm,
    now,
    safe_url,
    score,
    stats,
)


def _placeholder(sql: str, postgres: bool) -> str:
    return sql.replace("?", "%s") if postgres else sql


def _safe_url_cached(url: str, cache: dict[str, bool]) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        key = f"{parsed.scheme}://{parsed.hostname}:{parsed.port or (443 if parsed.scheme == 'https' else 80)}"
    except ValueError:
        return False
    if key not in cache:
        cache[key] = safe_url(key)
    return cache[key]


def fast_sync() -> dict:
    """Synchronize public/authorized live catalog using batched DB transactions.

    The legacy sync committed one row at a time, which is extremely slow with
    PostgreSQL in Docker. This implementation downloads the source APIs in
    parallel, validates hosts once per origin, and uses executemany batches.
    Existing stream health/publication state is preserved during metadata sync.
    """
    init_db()
    started = now()

    def fetch_one(item):
        name, url = item
        with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": "GaloDoidoTV/0.3"}) as client:
            return name, client.get(url).raise_for_status().json()

    with ThreadPoolExecutor(max_workers=len(API_URLS)) as pool:
        payload = dict(pool.map(fetch_one, API_URLS.items()))

    blocked = {
        item.get("channel"): item
        for item in payload["blocklist"]
        if item.get("channel") and item.get("reason") in {"dmca", "nsfw"}
    }
    logos: dict[str, str] = {}
    for logo in payload["logos"]:
        cid = logo.get("channel")
        if cid and logo.get("in_use") and cid not in logos:
            logos[cid] = logo.get("url")

    channel_rows = []
    allowed_channel_ids: set[str] = set()
    channels_by_id = {item.get("id"): item for item in payload["channels"] if item.get("id")}
    timestamp = now()
    for cid, channel in channels_by_id.items():
        if cid in blocked or channel.get("is_nsfw"):
            continue
        channel_rows.append((
            cid,
            channel.get("name", cid),
            channel.get("country"),
            json.dumps(channel.get("categories", [])),
            json.dumps(channel.get("alt_names", [])),
            logos.get(cid),
            canonical(channel.get("name", cid), cid),
            timestamp,
        ))
        allowed_channel_ids.add(cid)

    safe_cache: dict[str, bool] = {}
    stream_rows = []
    stream_channel_ids: set[str] = set()
    for stream in payload["streams"]:
        cid = stream.get("channel")
        url = stream.get("url", "")
        # Streams must reference the exact filtered set that is actually inserted
        # into channels. Checking only channels_by_id allowed NSFW channels to
        # slip through and violate the PostgreSQL foreign key.
        if not cid or cid not in allowed_channel_ids or not _safe_url_cached(url, safe_cache):
            continue
        sid = hashlib.sha1((cid + "|" + (stream.get("feed") or "") + "|" + url).encode()).hexdigest()
        stream_rows.append((
            sid, cid, stream.get("feed"), stream.get("title"), url,
            stream.get("referrer"), stream.get("user_agent"), stream.get("quality"),
            stream.get("label"), "iptv-org", score(stream), timestamp,
        ))
        stream_channel_ids.add(cid)

    block_rows = [
        (cid, item.get("reason"), item.get("ref"), timestamp)
        for cid, item in blocked.items()
    ]

    guide_rows = []
    seen_guides: set[str] = set()
    for entry in payload["guides"]:
        cid = entry.get("channel")
        if cid not in stream_channel_ids or cid in seen_guides:
            continue
        source = (entry.get("sources") or [{}])[0]
        if not source.get("url"):
            continue
        guide_rows.append((cid, entry.get("feed"), entry.get("site"), entry.get("site_id"), source.get("url"), timestamp))
        seen_guides.add(cid)

    conn = db_connect()
    postgres = not conn.__class__.__module__.startswith("sqlite3")
    try:
        cur = conn.cursor()
        if block_rows:
            cur.executemany(_placeholder(
                "INSERT INTO blocklist(channel_id,reason,ref,updated_at) VALUES(?,?,?,?) "
                "ON CONFLICT(channel_id) DO UPDATE SET reason=excluded.reason,ref=excluded.ref,updated_at=excluded.updated_at",
                postgres,
            ), block_rows)
        if channel_rows:
            cur.executemany(_placeholder(
                "INSERT INTO channels(id,name,country,categories,alt_names,logo,canonical_channel_id,updated_at) VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name,country=excluded.country,categories=excluded.categories,"
                "alt_names=excluded.alt_names,logo=excluded.logo,canonical_channel_id=excluded.canonical_channel_id,updated_at=excluded.updated_at",
                postgres,
            ), channel_rows)
        if stream_rows:
            cur.executemany(_placeholder(
                "INSERT INTO streams(id,channel_id,feed,title,url,referrer,user_agent,quality,label,source,score,last_checked) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET channel_id=excluded.channel_id,feed=excluded.feed,title=excluded.title,url=excluded.url,"
                "referrer=excluded.referrer,user_agent=excluded.user_agent,quality=excluded.quality,label=excluded.label,source=excluded.source,score=excluded.score",
                postgres,
            ), stream_rows)
        if guide_rows:
            cur.executemany(_placeholder(
                "INSERT INTO epg_sources(channel_id,feed,site,site_id,source_url,updated_at) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(channel_id) DO UPDATE SET feed=excluded.feed,site=excluded.site,site_id=excluded.site_id,source_url=excluded.source_url,updated_at=excluded.updated_at",
                postgres,
            ), guide_rows)
        conn.commit()
    finally:
        conn.close()

    # Free-TV is independent; parse once and insert in one batch.
    free_rows = []
    try:
        text = httpx.get(FREE_TV_URL, timeout=60, follow_redirects=True, headers={"User-Agent": "GaloDoidoTV/0.3"}).raise_for_status().text
        conn = db_connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id,name FROM channels")
            name_map = {norm(name): cid for cid, name in cur.fetchall()}
        finally:
            conn.close()
        current = {}
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("#EXTINF"):
                attrs = dict(re.findall(r'(\w[\w-]*)="([^"]*)"', line))
                current = {"name": line.split(",", 1)[1].strip() if "," in line else attrs.get("tvg-name", ""), "attrs": attrs}
            elif line and not line.startswith("#") and current:
                cid = name_map.get(norm(current["name"]))
                if cid and _safe_url_cached(line, safe_cache):
                    attrs = current["attrs"]
                    sid = hashlib.sha1((cid + "|free-tv|" + line).encode()).hexdigest()
                    free_rows.append((
                        sid, cid, attrs.get("tvg-id"), current["name"], line,
                        attrs.get("http-referrer"), attrs.get("http-user-agent"), attrs.get("quality"),
                        None, "free-tv", score({"url": line, "quality": attrs.get("quality")}), timestamp,
                    ))
                current = {}
    except httpx.HTTPError:
        free_rows = []

    if free_rows:
        conn = db_connect()
        postgres = not conn.__class__.__module__.startswith("sqlite3")
        try:
            cur = conn.cursor()
            cur.executemany(_placeholder(
                "INSERT INTO streams(id,channel_id,feed,title,url,referrer,user_agent,quality,label,source,score,last_checked) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET channel_id=excluded.channel_id,feed=excluded.feed,title=excluded.title,url=excluded.url,"
                "referrer=excluded.referrer,user_agent=excluded.user_agent,quality=excluded.quality,label=excluded.label,source=excluded.source,score=excluded.score",
                postgres,
            ), free_rows)
            conn.commit()
        finally:
            conn.close()

    conn = db_connect()
    postgres = not conn.__class__.__module__.startswith("sqlite3")
    try:
        cur = conn.cursor()
        cur.execute("UPDATE streams SET primary_stream=0")
        cur.execute(
            "UPDATE streams SET primary_stream=1 WHERE id IN ("
            "SELECT id FROM streams s WHERE score=(SELECT MAX(score) FROM streams s2 WHERE s2.channel_id=s.channel_id)"
            ")"
        )
        cur.execute(_placeholder(
            "UPDATE channels SET published=CASE WHEN id IN (SELECT channel_id FROM streams WHERE score>=? AND status IN ('healthy','degraded') GROUP BY channel_id) THEN 1 ELSE 0 END",
            postgres,
        ), (MIN_SCORE,))
        cur.execute(_placeholder(
            "INSERT INTO sync_runs(source,started_at,finished_at,discovered,published) VALUES(?,?,?,?,?)",
            postgres,
        ), ("iptv-org", started, now(), len(stream_rows) + len(free_rows), 0))
        conn.commit()
    finally:
        conn.close()

    export_files()
    result = stats()
    result.update({
        "status": "ok",
        "streams_imported": len(stream_rows) + len(free_rows),
        "channels_imported": len(channel_rows),
        "epg_sources_imported": len(guide_rows),
        "validated_origins": len(safe_cache),
    })
    return result
