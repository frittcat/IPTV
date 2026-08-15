from __future__ import annotations

import hashlib
import json
import ipaddress
import socket
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import os
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from backend.security import require_admin
from backend.dispatcharr import DispatcharrClient

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CONFIG = ROOT / "config" / "sources.yaml"
DB_URL = os.getenv("DATABASE_URL", "sqlite:///./data/familystream.db")
MIN_SCORE = int(os.getenv("PUBLISH_MIN_SCORE", "60"))

app = FastAPI(title="FamilyStream Hub", version="0.2.0")
app.mount("/admin", StaticFiles(directory=ROOT / "frontend", html=True), name="admin")

@app.middleware("http")
async def protect_admin(request: Request, call_next):
    if request.url.path.startswith("/admin"):
        try:
            require_admin(request)
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers or {})
    return await call_next(request)

API_URLS = {
    "channels": "https://iptv-org.github.io/api/channels.json",
    "streams": "https://iptv-org.github.io/api/streams.json",
    "feeds": "https://iptv-org.github.io/api/feeds.json",
    "logos": "https://iptv-org.github.io/api/logos.json",
    "guides": "https://iptv-org.github.io/api/guides.json",
    "blocklist": "https://iptv-org.github.io/api/blocklist.json",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def db_connect():
    if DB_URL.startswith("sqlite"):
        DATA.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(DATA / "familystream.db")
    import psycopg
    return psycopg.connect(DB_URL)


def db_execute(sql: str, params: tuple = (), fetch: bool = False):
    is_pg = not DB_URL.startswith("sqlite")
    if is_pg:
        sql = sql.replace("?", "%s")
        match = re.match(r"\s*INSERT OR REPLACE INTO (\w+)\(([^)]+)\) VALUES\(([^)]+)\)", sql, re.I)
        if match:
            table, columns, _values = match.groups()
            cols = [x.strip() for x in columns.split(",")]
            key = cols[0]
            updates = ", ".join(f"{col}=EXCLUDED.{col}" for col in cols[1:])
            sql = re.sub(r"INSERT OR REPLACE INTO", "INSERT INTO", sql, count=1, flags=re.I)
            sql += f" ON CONFLICT ({key}) DO UPDATE SET {updates}"
        elif sql.lstrip().upper().startswith("INSERT INTO") and "ON CONFLICT" not in sql.upper():
            sql += " ON CONFLICT DO NOTHING"
    conn = db_connect()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall() if fetch else None
        conn.commit()
        return rows
    finally:
        conn.close()


def init_db():
    stmts = [
        "CREATE TABLE IF NOT EXISTS channels (id TEXT PRIMARY KEY, name TEXT NOT NULL, country TEXT, categories TEXT, alt_names TEXT, logo TEXT, published INTEGER DEFAULT 0, canonical_channel_id TEXT, updated_at TEXT)",
        "CREATE TABLE IF NOT EXISTS streams (id TEXT PRIMARY KEY, channel_id TEXT, feed TEXT, title TEXT, url TEXT NOT NULL, referrer TEXT, user_agent TEXT, quality TEXT, label TEXT, source TEXT, status TEXT DEFAULT 'new', score REAL DEFAULT 0, primary_stream INTEGER DEFAULT 0, last_checked TEXT, last_success TEXT, failure_count INTEGER DEFAULT 0, FOREIGN KEY(channel_id) REFERENCES channels(id))",
        "CREATE TABLE IF NOT EXISTS blocklist (channel_id TEXT PRIMARY KEY, reason TEXT, ref TEXT, updated_at TEXT)",
        "CREATE TABLE IF NOT EXISTS sync_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, started_at TEXT, finished_at TEXT, discovered INTEGER DEFAULT 0, published INTEGER DEFAULT 0, error TEXT)",
        "CREATE TABLE IF NOT EXISTS epg_sources (channel_id TEXT PRIMARY KEY, feed TEXT, site TEXT, site_id TEXT, source_url TEXT, updated_at TEXT)",
        "CREATE TABLE IF NOT EXISTS vod_items (id TEXT PRIMARY KEY, title TEXT, year TEXT, description TEXT, stream_url TEXT, source_url TEXT, license TEXT, license_url TEXT, creator TEXT, attribution TEXT, published INTEGER DEFAULT 0, retrieved_at TEXT)",
    ]
    conn = db_connect()
    try:
        cur = conn.cursor()
        for stmt in stmts:
            if not DB_URL.startswith("sqlite"):
                stmt = stmt.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
            cur.execute(stmt)
        for migration in sorted((ROOT / "migrations").glob("*.sql")):
            for stmt in migration.read_text(encoding="utf-8").split(";"):
                stmt = stmt.strip()
                if stmt:
                    if not DB_URL.startswith("sqlite"):
                        stmt = stmt.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
                    cur.execute(stmt)
        conn.commit()
    finally:
        conn.close()


def norm(value: str | None) -> str:
    value = value or ""
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"\b(hd|fhd|uhd|4k|1080p|720p|576p|480p|sd)\b", "", value)
    return re.sub(r"[^a-z0-9]+", "", value)


def canonical(name: str, channel_id: str) -> str:
    return channel_id or norm(name)


def score(stream: dict[str, Any]) -> float:
    q = (stream.get("quality") or "").lower()
    value = 35.0
    value += {"1080p": 35, "1080i": 30, "720p": 25, "576p": 15, "480p": 10}.get(q, 5)
    if str(stream.get("url", "")).startswith("https://"): value += 10
    if not stream.get("referrer") and not stream.get("user_agent"): value += 10
    if stream.get("label"): value -= 15
    return max(0, min(100, value))


def safe_url(url: str, trusted: bool = False) -> bool:
    p = urlparse(url)
    if p.scheme not in {"http", "https"} or not p.hostname:
        return False
    if trusted:
        return True
    host = p.hostname.strip("[]").lower()
    if host in {"localhost", "metadata.google.internal", "metadata", "169.254.169.254"}:
        return False
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            addresses = {ipaddress.ip_address(x[4][0]) for x in socket.getaddrinfo(host, p.port or 443, type=socket.SOCK_STREAM)}
        except OSError:
            return False
    return all(not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified) for ip in addresses)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok", "time": now()}


@app.get("/api/stats")
def stats():
    init_db()
    queries = {
        "channels_discovered": "SELECT COUNT(*) FROM channels",
        "channels_published": "SELECT COUNT(*) FROM channels WHERE published=1",
        "healthy_streams": "SELECT COUNT(*) FROM streams WHERE status='healthy'",
        "degraded_streams": "SELECT COUNT(*) FROM streams WHERE status='degraded'",
        "offline_streams": "SELECT COUNT(*) FROM streams WHERE status='offline'",
        "fallback_streams": "SELECT COUNT(*) FROM streams WHERE primary_stream=0 AND score>=60",
        "vod_items": "SELECT COUNT(*) FROM vod_items WHERE published=1",
        "with_epg": "SELECT COUNT(*) FROM epg_sources",
    }
    result = {}
    for key, sql in queries.items():
        result[key] = db_execute(sql, fetch=True)[0][0]
    for code, key in [("BR", "brazil"), ("FR", "france"), ("PT", "portugal")]:
        result[key] = db_execute("SELECT COUNT(*) FROM channels WHERE published=1 AND country=?", (code,), fetch=True)[0][0]
    result["international"] = db_execute("SELECT COUNT(*) FROM channels WHERE published=1 AND country NOT IN ('BR','FR','PT')", fetch=True)[0][0]
    return result


@app.get("/api/channels")
def channels(q: str = Query(""), country: str = Query(""), category: str = Query(""), published: bool | None = None):
    clauses, params = [], []
    if q: clauses.append("(lower(name) LIKE ? OR lower(alt_names) LIKE ?)"); params += [f"%{q.lower()}%", f"%{q.lower()}%"]
    if country: clauses.append("country=?"); params.append(country.upper())
    if category: clauses.append("categories LIKE ?"); params.append(f"%{category}%")
    if published is not None: clauses.append("published=?"); params.append(int(published))
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = db_execute(f"SELECT id,name,country,categories,logo,published FROM channels{where} ORDER BY country,name", tuple(params), True)
    return [dict(zip(["id","name","country","categories","logo","published"], r)) for r in rows]


@app.post("/api/sync")
@app.post("/api/v1/live/sync")
def sync(_admin: str = Depends(require_admin)):
    init_db()
    started = now()
    try:
        def fetch_one(item):
            name, url = item
            with httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": "FamilyStream-Hub/0.1"}) as client:
                return name, client.get(url).raise_for_status().json()
        with ThreadPoolExecutor(max_workers=len(API_URLS)) as pool:
            payload = dict(pool.map(fetch_one, API_URLS.items()))
        blocked = {x.get("channel"): x for x in payload["blocklist"] if x.get("reason") in {"dmca", "nsfw"}}
        for item in blocked.values():
            db_execute("INSERT OR REPLACE INTO blocklist(channel_id,reason,ref,updated_at) VALUES(?,?,?,?)", (item.get("channel"), item.get("reason"), item.get("ref"), now()))
        logos = {}
        for logo in payload["logos"]:
            if logo.get("in_use") and logo.get("channel") not in logos: logos[logo.get("channel")] = logo.get("url")
        channels_by_id = {x.get("id"): x for x in payload["channels"]}
        for cid, ch in channels_by_id.items():
            if cid in blocked or ch.get("is_nsfw"): continue
            db_execute("INSERT OR REPLACE INTO channels(id,name,country,categories,alt_names,logo,published,canonical_channel_id,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (cid, ch.get("name", cid), ch.get("country"), json.dumps(ch.get("categories", [])), json.dumps(ch.get("alt_names", [])), logos.get(cid), 0, canonical(ch.get("name", cid), cid), now()))
        count = 0
        for s in payload["streams"]:
            cid = s.get("channel")
            if not cid or cid in blocked or not safe_url(s.get("url", "")): continue
            sid = hashlib.sha1((cid + "|" + (s.get("feed") or "") + "|" + s.get("url", "")).encode()).hexdigest()
            sc = score(s)
            db_execute("INSERT OR REPLACE INTO streams(id,channel_id,feed,title,url,referrer,user_agent,quality,label,source,status,score,last_checked) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (sid,cid,s.get("feed"),s.get("title"),s.get("url"),s.get("referrer"),s.get("user_agent"),s.get("quality"),s.get("label"),"iptv-org", "new", sc, now()))
            count += 1
        # Free-TV is an independent live source; map it to known channels by normalized name.
        try:
            free_text = httpx.get(FREE_TV_URL, timeout=60, follow_redirects=True, headers={"User-Agent":"FamilyStream-Hub/0.2"}).raise_for_status().text
            channel_rows = db_execute("SELECT id,name FROM channels", fetch=True)
            name_map = {norm(name): cid for cid, name in channel_rows}
            current = {}
            for line in free_text.splitlines():
                line = line.strip()
                if line.startswith("#EXTINF"):
                    attrs = dict(re.findall(r'(\w[\w-]*)="([^"]*)"', line))
                    current = {"name": line.split(",",1)[1].strip() if "," in line else attrs.get("tvg-name", ""), "attrs": attrs}
                elif line and not line.startswith("#") and current:
                    cid = name_map.get(norm(current["name"]))
                    if cid and safe_url(line):
                        sid = hashlib.sha1((cid + "|free-tv|" + line).encode()).hexdigest()
                        attrs = current["attrs"]
                        db_execute("INSERT INTO streams(id,channel_id,feed,title,url,referrer,user_agent,quality,label,source,status,score,last_checked) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET url=excluded.url,title=excluded.title,quality=excluded.quality,label=excluded.label,source=excluded.source,last_checked=excluded.last_checked", (sid,cid,attrs.get("tvg-id"),current["name"],line,attrs.get("http-referrer"),attrs.get("http-user-agent"),attrs.get("quality"),None,"free-tv","new",score({"url":line,"quality":attrs.get("quality")}),now()))
                    current = {}
        except httpx.HTTPError:
            pass
        stream_channel_ids = {s.get("channel") for s in payload["streams"] if s.get("channel")}
        seen_guides = set()
        for e in payload["guides"]:
            cid = e.get("channel")
            if cid not in stream_channel_ids or cid in seen_guides:
                continue
            src = (e.get("sources") or [{}])[0]
            if not src.get("url"):
                continue
            db_execute("INSERT OR REPLACE INTO epg_sources(channel_id,feed,site,site_id,source_url,updated_at) VALUES(?,?,?,?,?,?)", (cid,e.get("feed"),e.get("site"),e.get("site_id"),src.get("url"),now()))
            seen_guides.add(cid)
        db_execute("UPDATE channels SET published=CASE WHEN id IN (SELECT channel_id FROM streams WHERE score>=? AND status IN ('healthy','degraded') GROUP BY channel_id) THEN 1 ELSE 0 END", (MIN_SCORE,))
        db_execute("UPDATE streams SET primary_stream=0")
        db_execute("UPDATE streams SET primary_stream=1 WHERE id IN (SELECT id FROM streams s WHERE score=(SELECT MAX(score) FROM streams s2 WHERE s2.channel_id=s.channel_id))")
        finished = now()
        db_execute("INSERT INTO sync_runs(source,started_at,finished_at,discovered,published) VALUES(?,?,?,?,?)", ("iptv-org",started,finished,count,db_execute("SELECT COUNT(*) FROM channels WHERE published=1",fetch=True)[0][0]))
        export_files()
        return {"status":"ok", "streams_imported":count, "stats":stats()}
    except Exception as exc:
        db_execute("INSERT INTO sync_runs(source,started_at,finished_at,error) VALUES(?,?,?,?)", ("iptv-org",started,now(),str(exc)))
        raise HTTPException(502, f"sync failed: {exc}")


def export_files():
    DATA.mkdir(exist_ok=True)
    rows = db_execute("SELECT c.id,c.name,c.country,c.categories,c.logo,s.url,s.referrer,s.user_agent FROM channels c JOIN streams s ON s.channel_id=c.id WHERE c.published=1 AND s.status IN ('healthy','degraded') AND s.score>=? ORDER BY c.country,c.name,s.score DESC", (MIN_SCORE,), True)
    seen, lines = set(), ["#EXTM3U"]
    for r in rows:
        if r[0] in seen: continue
        seen.add(r[0])
        cats = []
        try: cats = json.loads(r[3] or "[]")
        except (TypeError, json.JSONDecodeError): pass
        group = " | ".join(x.replace("_", " ").title() for x in cats[:2]) or "General"
        group = f"{r[2] or 'International'} | {group}"
        attrs = {"tvg-id": r[0], "tvg-name": r[1], "tvg-country": r[2] or "", "group-title": group}
        if r[4]: attrs["tvg-logo"] = r[4]
        attr_text = " ".join(f'{k}="{str(v).replace(chr(34), chr(39))}"' for k,v in attrs.items())
        if r[7]: attr_text += f' http-user-agent="{r[7].replace(chr(34), chr(39))}"'
        if r[6]: attr_text += f' http-referrer="{r[6].replace(chr(34), chr(39))}"'
        stable_base = os.getenv("FAMILYSTREAM_PUBLIC_URL", "http://localhost:8080")
        lines += [f"#EXTINF:-1 {attr_text},{r[1]}", f"{stable_base}/live/stream/{r[0]}"]
    (DATA / "family-tv.m3u").write_text("\n".join(lines) + "\n", encoding="utf-8")
    root = ET.Element("tv", {"generator-info-name": "FamilyStream Hub"})
    emitted = set()
    for r in rows:
        if r[0] in emitted: continue
        emitted.add(r[0]); node = ET.SubElement(root, "channel", {"id": r[0]}); ET.SubElement(node, "display-name").text = r[1]
    # Import a bounded number of provider programmes and keep the rest as guide sources.
    epg_rows = db_execute("SELECT channel_id,source_url FROM epg_sources WHERE source_url IS NOT NULL LIMIT 100", fetch=True)
    for cid, source_url in epg_rows:
        try:
            text = httpx.get(source_url, timeout=10, follow_redirects=True, headers={"User-Agent":"FamilyStream-Hub/0.2"}).text
            parsed = ET.fromstring(text)
            for programme in parsed.findall("programme")[:500]:
                if programme.attrib.get("channel") not in {x[0] for x in emitted}: continue
                attrs = {k: v for k,v in programme.attrib.items() if k in {"start","stop","channel"}}
                out = ET.SubElement(root, "programme", attrs)
                for tag in ("title","sub-title","desc","category","episode-num","icon"):
                    child = programme.find(tag)
                    if child is not None:
                        copy = ET.SubElement(out, tag, child.attrib); copy.text = child.text
        except (httpx.HTTPError, ET.ParseError, ValueError):
            continue
    ET.ElementTree(root).write(DATA / "family-tv.xml", encoding="utf-8", xml_declaration=True)


@app.get("/family-tv.m3u", response_class=PlainTextResponse)
def playlist():
    path = DATA / "family-tv.m3u"
    if not path.exists(): export_files()
    return path.read_text(encoding="utf-8")


@app.get("/family-tv.xml", response_class=PlainTextResponse)
def xmltv():
    path = DATA / "family-tv.xml"
    if not path.exists(): export_files()
    return path.read_text(encoding="utf-8")


@app.get("/api/health-check")
def health_check(limit: int = Query(20, ge=1, le=100)):
    rows = db_execute("SELECT id,url FROM streams ORDER BY score DESC LIMIT ?", (limit,), True)
    results = []
    with httpx.Client(timeout=8, follow_redirects=True, headers={"User-Agent": "FamilyStream-Hub/0.1"}) as client:
        for sid, url in rows:
            status, ok = "offline", False
            started = datetime.now().timestamp()
            try:
                stream_row = db_execute("SELECT referrer,user_agent FROM streams WHERE id=?", (sid,), True)[0]
                headers = {}
                if stream_row[0]: headers["Referer"] = stream_row[0]
                if stream_row[1]: headers["User-Agent"] = stream_row[1]
                response = client.get(url, headers={**headers, "Range": "bytes=0-8191"})
                latency_ms = round((datetime.now().timestamp() - started) * 1000, 2)
                text = response.text[:200000] if "text" in response.headers.get("content-type", "") or url.endswith(".m3u8") else ""
                ok = response.status_code < 400 and ("#EXTM3U" in text or "mpegurl" in response.headers.get("content-type", "") or response.status_code in (200,206))
                status = "healthy" if ok else "degraded"
                db_execute("INSERT INTO stream_health(stream_id,http_status,manifest_latency_ms,status,error,checked_at) VALUES(?,?,?,?,?,?)", (sid,response.status_code,latency_ms,status,None,now()))
            except httpx.HTTPError as exc:
                db_execute("INSERT INTO stream_health(stream_id,status,error,checked_at) VALUES(?,?,?,?)", (sid,status,str(exc)[:500],now()))
            db_execute("UPDATE streams SET status=?,last_checked=?,last_success=CASE WHEN ?=1 THEN ? ELSE last_success END,failure_count=CASE WHEN ?=1 THEN 0 ELSE failure_count+1 END WHERE id=?", (status, now(), int(ok), now(), int(ok), sid))
            results.append({"id": sid, "status": status})
    db_execute("UPDATE channels SET published=CASE WHEN id IN (SELECT channel_id FROM streams WHERE status IN ('healthy','degraded') AND score>=? GROUP BY channel_id) THEN 1 ELSE 0 END", (MIN_SCORE,))
    export_files()
    return {"checked": len(results), "results": results}


@app.get("/api/report")
def report():
    report = {"generated_at": now(), **stats()}
    (DATA / "reports").mkdir(parents=True, exist_ok=True)
    (DATA / "reports" / "latest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (DATA / "reports" / "latest.md").write_text("# FamilyStream Hub — relatório\n\n```json\n" + json.dumps(report, indent=2) + "\n```\n", encoding="utf-8")
    return report


@app.get("/", response_class=FileResponse)
def root():
    return FileResponse(ROOT / "frontend" / "index.html")


# ---- v0.2 VOD ----
from providers.base import VODItem
from providers.archive_org import ArchiveOrgProvider
from providers.public_media import WikimediaProvider, NASAProvider
from providers.service import generate_strm, item_key, upsert_vod_item

FREE_TV_URL = "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8"


def vod_provider_items(provider: str, limit: int = 10):
    if provider == "archive_org": return ArchiveOrgProvider(rows=min(limit, 50)).discover(pages=1)
    if provider == "wikimedia_commons": return WikimediaProvider().discover(limit=limit)
    if provider == "nasa": return NASAProvider().discover(limit=limit)
    raise HTTPException(400, "provider must be archive_org, wikimedia_commons or nasa")


@app.post("/api/v1/vod/sync")
def vod_sync(provider: str = Query("archive_org"), limit: int = Query(10, ge=1, le=100), _admin: str = Depends(require_admin)):
    init_db(); started = now(); count = 0; approved = 0
    try:
        for item in vod_provider_items(provider, limit):
            if not item.stream_url or not safe_url(item.stream_url):
                continue
            vid = upsert_vod_item(db_execute, item)
            if item.rights_status == "approved":
                generate_strm(item, vid, DATA / "vod", os.getenv("FAMILYSTREAM_PUBLIC_URL", "http://localhost:8080")); approved += 1
            count += 1
        db_execute("INSERT INTO vod_sync_runs(provider_id,started_at,finished_at,new_items) VALUES(?,?,?,?)", (provider, started, now(), count))
        return {"status":"ok", "provider":provider, "items":count, "rights_approved":approved}
    except Exception as exc:
        db_execute("INSERT INTO vod_sync_runs(provider_id,started_at,finished_at,error) VALUES(?,?,?,?)", (provider, started, now(), str(exc)))
        raise HTTPException(502, f"vod sync failed: {exc}")


@app.get("/api/v1/vod")
def vod_catalog(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), q: str = Query(""), item_type: str = Query("movie")):
    offset = (page - 1) * page_size
    table = "vod_movies" if item_type == "movie" else "vod_series"
    where = "WHERE published=1"
    params: tuple = ()
    if q:
        where += " AND lower(title) LIKE ?"; params = (f"%{q.lower()}%",)
    rows = db_execute(f"SELECT id,title,year,plot,poster,rights_status,stream_status,first_seen,last_seen FROM {table} {where} ORDER BY last_seen DESC LIMIT ? OFFSET ?", params + (page_size, offset), True)
    keys = ["id","title","year","plot","poster","rights_status","stream_status","first_seen","last_seen"]
    return {"page":page, "page_size":page_size, "items":[dict(zip(keys,r)) for r in rows]}


def _vod_urls(vod_id: str):
    return db_execute("SELECT id,url,headers_json FROM vod_streams WHERE item_id=? ORDER BY is_primary DESC,score DESC", (vod_id,), True)


@app.api_route("/vod/stream/{vod_id}", methods=["GET", "HEAD"])
def vod_stream(vod_id: str, request: Request):
    candidates = _vod_urls(vod_id)
    if not candidates: raise HTTPException(404, "VOD stream not found")
    selected = None
    for sid, url, headers_json in candidates:
        if not safe_url(url): continue
        try:
            with httpx.Client(timeout=12, follow_redirects=True) as client:
                probe = client.head(url, headers=json.loads(headers_json or "{}"))
                if probe.status_code < 500:
                    selected = (sid, url, json.loads(headers_json or "{}")); break
        except httpx.HTTPError:
            continue
    if not selected: raise HTTPException(502, "No VOD upstream is currently reachable")
    sid, url, upstream_headers = selected
    request_headers = dict(upstream_headers)
    if request.headers.get("range"): request_headers["Range"] = request.headers["range"]
    if request.method == "HEAD":
        with httpx.Client(timeout=12, follow_redirects=True) as client:
            response = client.head(url, headers=request_headers)
        return PlainTextResponse("", status_code=response.status_code, headers={k:v for k,v in response.headers.items() if k.lower() in {"content-length","content-type","accept-ranges","etag","last-modified","content-range"}})
    def body():
        with httpx.stream("GET", url, headers=request_headers, timeout=30, follow_redirects=True) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes(1024 * 256): yield chunk
    return StreamingResponse(body(), media_type="application/octet-stream", headers={"Accept-Ranges":"bytes"})


@app.get("/api/v1/vod/stats")
def vod_stats():
    init_db()
    result = {}
    for key, sql in {"movies":"SELECT COUNT(*) FROM vod_movies", "series":"SELECT COUNT(*) FROM vod_series", "episodes":"SELECT COUNT(*) FROM vod_episodes", "published_movies":"SELECT COUNT(*) FROM vod_movies WHERE published=1", "rights_approved":"SELECT COUNT(*) FROM vod_rights WHERE rights_status='approved'", "rights_review":"SELECT COUNT(*) FROM vod_rights WHERE rights_status='review_required'"}.items():
        result[key] = db_execute(sql, fetch=True)[0][0]
    return result


@app.api_route("/live/stream/{channel_id}", methods=["GET", "HEAD"])
def live_stream(channel_id: str, request: Request):
    candidates = db_execute("SELECT id,url,referrer,user_agent FROM streams WHERE channel_id=? AND status IN ('healthy','degraded') ORDER BY primary_stream DESC,score DESC", (channel_id,), True)
    selected = None
    for sid, url, referrer, user_agent in candidates:
        if not safe_url(url): continue
        headers = {"User-Agent": user_agent} if user_agent else {}
        if referrer: headers["Referer"] = referrer
        if request.headers.get("range"): headers["Range"] = request.headers["range"]
        try:
            if request.method == "HEAD":
                with httpx.Client(timeout=8, follow_redirects=True) as client: probe = client.head(url, headers=headers)
            else:
                with httpx.Client(timeout=8, follow_redirects=True) as client: probe = client.head(url, headers=headers)
            if probe.status_code < 500:
                selected = (sid, url, headers); break
        except httpx.HTTPError:
            continue
    if not selected: raise HTTPException(502, "No healthy live stream is available")
    sid, url, headers = selected
    if request.method == "HEAD":
        with httpx.Client(timeout=8, follow_redirects=True) as client: response = client.head(url, headers=headers)
        return PlainTextResponse("", status_code=response.status_code, headers={k:v for k,v in response.headers.items() if k.lower() in {"content-length","content-type","accept-ranges","etag","last-modified","content-range"}})
    def body():
        with httpx.stream("GET", url, headers=headers, timeout=30, follow_redirects=True) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes(1024 * 256): yield chunk
    return StreamingResponse(body(), media_type="application/vnd.apple.mpegurl", headers={"Accept-Ranges":"bytes"})


@app.get("/admin/vod", response_class=FileResponse)
def admin_vod():
    return FileResponse(ROOT / "frontend" / "vod.html")


@app.get("/api/v1/dispatcharr/status")
def dispatcharr_status():
    client = DispatcharrClient()
    return client.status()


@app.get("/api/v1/dispatcharr/integration-plan")
def dispatcharr_integration_plan():
    return DispatcharrClient().integration_plan()
