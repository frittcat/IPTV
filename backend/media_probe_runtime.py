from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.gateway_runtime import SESSIONS
from backend.media_probe import persist_probe, run_ffprobe
from backend.security import require_admin
from backend.streaming_gateway import UpstreamCandidate

router = APIRouter()


def _db_execute(sql: str, params: tuple = (), fetch: bool = False):
    from backend.app import db_execute

    return db_execute(sql, params, fetch)


def _safe_url(url: str) -> bool:
    from backend.app import safe_url

    return safe_url(url)


def _candidate(kind: str, stream_id: str) -> UpstreamCandidate | None:
    if kind == "live":
        rows = _db_execute(
            "SELECT id,url,referrer,user_agent,score FROM streams WHERE id=? LIMIT 1",
            (stream_id,),
            True,
        )
        if not rows:
            return None
        sid, url, referrer, user_agent, score = rows[0]
        headers: dict[str, str] = {}
        if user_agent:
            headers["User-Agent"] = user_agent
        if referrer:
            headers["Referer"] = referrer
        return UpstreamCandidate(sid, url, headers, float(score or 0))

    if kind == "vod":
        rows = _db_execute(
            "SELECT id,url,headers_json,score FROM vod_streams WHERE id=? LIMIT 1",
            (stream_id,),
            True,
        )
        if not rows:
            return None
        sid, url, headers_json, score = rows[0]
        try:
            raw_headers = json.loads(headers_json or "{}")
            headers = raw_headers if isinstance(raw_headers, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            headers = {}
        return UpstreamCandidate(
            sid,
            url,
            {str(key): str(value) for key, value in headers.items()},
            float(score or 0),
        )

    return None


def _internal_base() -> str:
    # ffprobe talks back to FamilyStream using only an opaque local capability URL.
    # The provider URL and credentials remain in the server process memory.
    return os.getenv("FAMILYSTREAM_INTERNAL_URL", "http://127.0.0.1:8080").rstrip("/")


def _probe_target(candidate: UpstreamCandidate) -> str:
    if not _safe_url(candidate.url):
        raise HTTPException(502, "Unsafe media source")
    session = SESSIONS.create(candidate.headers, profile_id="media-probe")
    resource_id = SESSIONS.register(session.id, candidate.url)
    return f"{_internal_base()}/api/v1/gateway/hls/{session.id}/{resource_id}"


@router.post("/api/v1/playback/probe/{kind}/{stream_id}")
def probe_stream(
    kind: str,
    stream_id: str,
    request: Request,
    timeout: int = Query(20, ge=3, le=60),
    _admin: str = Depends(require_admin),
):
    if kind not in {"live", "vod"}:
        raise HTTPException(400, "kind must be live or vod")
    candidate = _candidate(kind, stream_id)
    if candidate is None:
        raise HTTPException(404, "Stream not found")

    result = run_ffprobe(_probe_target(candidate), timeout_seconds=timeout)
    persist_probe(_db_execute, stream_id, kind, result)
    return {
        "stream_id": stream_id,
        "kind": kind,
        **result.public_dict(),
    }


@router.get("/api/v1/playback/technical/{kind}/{stream_id}")
def technical_profile(
    kind: str,
    stream_id: str,
    _admin: str = Depends(require_admin),
):
    if kind not in {"live", "vod"}:
        raise HTTPException(400, "kind must be live or vod")
    rows = _db_execute(
        "SELECT protocol,container,video_codec,audio_codec,width,height,bitrate,fps,hdr,audio_channels,probe_status,probed_at "
        "FROM stream_technical_profiles WHERE stream_id=? AND item_kind=?",
        (stream_id, kind),
        True,
    )
    if not rows:
        raise HTTPException(404, "Technical profile not found")
    keys = [
        "protocol",
        "container",
        "video_codec",
        "audio_codec",
        "width",
        "height",
        "bitrate",
        "fps",
        "hdr",
        "audio_channels",
        "probe_status",
        "probed_at",
    ]
    return {"stream_id": stream_id, "kind": kind, **dict(zip(keys, rows[0]))}
