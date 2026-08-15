from __future__ import annotations

import hashlib
import json
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
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CONFIG = ROOT / "config" / "sources.yaml"
DB_URL = os.getenv("DATABASE_URL", "sqlite:///./data/familystream.db")
MIN_SCORE = int(os.getenv("PUBLISH_MIN_SCORE", "60"))

app = FastAPI(title="FamilyStream Hub", version="0.1.0")
app.mount("/admin", StaticFiles(directory=ROOT / "frontend", html=True), name="admin")

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
        sql = sql.replace("?", "%s").replace("INSERT OR REPLACE INTO", "INSERT INTO")
        if sql.lstrip().upper().startswith("INSERT INTO") and "ON CONFLICT" not in sql.upper():
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


def safe_url(url: str) -> bool:
    p = urlparse(url)
    return p.scheme in {"http", "https"} and bool(p.netloc) and p.hostname not in {"localhost", "127.0.0.1", "::1"}


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


@app.get("/api/sync")
def sync():
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
        db_execute("UPDATE channels SET published=1 WHERE id IN (SELECT channel_id FROM streams WHERE score>=? GROUP BY channel_id)", (MIN_SCORE,))
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
    rows = db_execute("SELECT c.id,c.name,c.country,c.categories,c.logo,s.url,s.referrer,s.user_agent FROM channels c JOIN streams s ON s.channel_id=c.id WHERE c.published=1 AND s.score>=? ORDER BY c.country,c.name,s.score DESC", (MIN_SCORE,), True)
    seen, lines = set(), ["#EXTM3U"]
    for r in rows:
        if r[0] in seen: continue
        seen.add(r[0]); attrs = f'tvg-id="{r[0]}" tvg-name="{r[1]}" tvg-country="{r[2] or ""}" group-title="{r[3] or "general"}"'
        if r[7]: attrs += f' http-user-agent="{r[7]}"'
        if r[6]: attrs += f' http-referrer="{r[6]}"'
        lines += [f"#EXTINF:-1 {attrs},{r[1]}", r[5]]
    (DATA / "family-tv.m3u").write_text("\n".join(lines) + "\n", encoding="utf-8")
    channels_xml = []
    for r in rows:
        if r[0] in {x[0] for x in channels_xml}: continue
        channels_xml.append((r[0], r[1], r[8] if len(r)>8 else None))
    programmes = []
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<tv generator-info-name="FamilyStream Hub">']
    for cid, name, _ in channels_xml: xml.append(f'  <channel id="{cid}"><display-name>{name}</display-name></channel>')
    xml.append('</tv>')
    (DATA / "family-tv.xml").write_text("\n".join(xml) + "\n", encoding="utf-8")


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
            try:
                response = client.get(url, headers={"Range": "bytes=0-4095"})
                ok = response.status_code < 400
                status = "healthy" if ok else "degraded"
            except httpx.HTTPError:
                pass
            db_execute("UPDATE streams SET status=?,last_checked=?,last_success=CASE WHEN ?=1 THEN ? ELSE last_success END,failure_count=CASE WHEN ?=1 THEN 0 ELSE failure_count+1 END WHERE id=?", (status, now(), int(ok), now(), int(ok), sid))
            results.append({"id": sid, "status": status})
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
