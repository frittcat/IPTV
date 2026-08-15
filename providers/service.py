from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from .base import VODItem


def utcnow(): return datetime.now(timezone.utc).isoformat()


def item_key(item: VODItem) -> str:
    return hashlib.sha1(f"{item.provider_id}:{item.provider_item_id}:{item.item_type}".encode()).hexdigest()


def upsert_vod_item(db_execute, item: VODItem) -> str:
    key = item_key(item); t = utcnow(); payload = json.dumps(item.metadata, ensure_ascii=False)
    db_execute("INSERT INTO vod_movies(id,provider_id,provider_item_id,title,year,plot,genres,poster,stream_status,rights_status,first_seen,last_seen,published,canonical_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,year=excluded.year,plot=excluded.plot,genres=excluded.genres,poster=excluded.poster,stream_status=excluded.stream_status,rights_status=excluded.rights_status,last_seen=excluded.last_seen", (key,item.provider_id,item.provider_item_id,item.title,item.year,item.plot,json.dumps(item.genres),item.poster,"new",item.rights_status,t,t,int(item.rights_status=="approved"),key)) if item.item_type == "movie" else db_execute("INSERT INTO vod_series(id,provider_id,provider_series_id,title,year,plot,genres,poster,status,rights_status,first_seen,last_seen,published,canonical_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,year=excluded.year,plot=excluded.plot,genres=excluded.genres,poster=excluded.poster,status=excluded.status,rights_status=excluded.rights_status,last_seen=excluded.last_seen", (key,item.provider_id,item.provider_item_id,item.title,item.year,item.plot,json.dumps(item.genres),item.poster,"active",item.rights_status,t,t,int(item.rights_status=="approved"),key))
    if item.stream_url:
        sid = hashlib.sha1(f"{key}:{item.stream_url}".encode()).hexdigest()
        db_execute("INSERT INTO vod_streams(id,item_type,item_id,provider_id,url,quality,headers_json,status,score,is_primary) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET url=excluded.url,quality=excluded.quality,headers_json=excluded.headers_json,status=excluded.status", (sid,item.item_type,key,item.provider_id,item.stream_url,item.quality,json.dumps({}),"new",50,1))
    db_execute("INSERT INTO vod_rights(id,item_type,item_id,license,license_url,creator,attribution,rights_status,evidence_url,checked_at) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET license=excluded.license,license_url=excluded.license_url,rights_status=excluded.rights_status,checked_at=excluded.checked_at", (key,item.item_type,key,item.license,item.license_url,item.creator,item.attribution,item.rights_status,item.metadata.get("evidence_url"),t))
    return key


def generate_strm(item: VODItem, vod_id: str, root: Path, base_url: str = "http://localhost:8080") -> Path:
    if item.item_type == "movie":
        folder = root / "movies" / f"{item.title} ({item.year or 'unknown'}) [{vod_id[:8]}]"; filename = f"{item.title} ({item.year or 'unknown'}).strm"
    else:
        folder = root / "shows" / f"{item.title} ({item.year or 'unknown'}) [{vod_id[:8]}]" / "Season 01"; filename = f"{item.title} S01E01.strm"
    folder.mkdir(parents=True, exist_ok=True); path = folder / filename
    path.write_text(f"{base_url}/vod/stream/{vod_id}\n", encoding="utf-8")
    return path
