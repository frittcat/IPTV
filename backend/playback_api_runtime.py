from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

import backend.gateway_runtime as gateway
from backend.playback_resolver import profile_from_headers
from backend.streaming_gateway import upstream_status_usable

router = APIRouter()


def _candidates(kind: str, item_id: str):
    if kind == "live":
        return gateway._live_candidates(item_id), "live"
    if kind in {"vod", "episode"}:
        return gateway._vod_candidates(item_id), "vod"
    raise HTTPException(400, "kind must be live, vod or episode")


def _playback_path(kind: str, item_id: str) -> str:
    if kind == "live":
        return f"/api/v1/play/live/{item_id}"
    if kind == "episode":
        return f"/api/v1/play/episode/{item_id}"
    return f"/api/v1/play/vod/{item_id}"


def _mime_type(diagnostic: dict[str, object]) -> str | None:
    protocol = str(diagnostic.get("protocol") or "").lower()
    container = str(diagnostic.get("container") or "").lower()
    if protocol == "hls" or container == "hls":
        return "application/x-mpegURL"
    if container == "mp4":
        return "video/mp4"
    if container in {"mpegts", "ts"}:
        return "video/mp2t"
    if container in {"matroska", "mkv"}:
        return "video/x-matroska"
    return None


@router.get("/api/v1/playback/resolve/{kind}/{item_id}")
def resolve_playback(kind: str, item_id: str, request: Request):
    candidates, resolver_kind = _candidates(kind, item_id)
    if not candidates:
        raise HTTPException(404, "Playback item not found")

    profile = profile_from_headers(request.headers)
    ranked = gateway.rank_candidates(candidates, profile, resolver_kind)
    selected = None
    for candidate in ranked:
        status = gateway._probe(candidate)
        if status is not None and upstream_status_usable(status):
            selected = candidate
            break
    if selected is None:
        raise HTTPException(502, "No usable upstream media source")

    diagnostic = gateway.candidate_diagnostic(selected, profile, resolver_kind)
    path = _playback_path(kind, item_id)
    return {
        "kind": kind,
        "item_id": item_id,
        "profile": profile.id,
        "playback_url": f"{gateway._client_base(request)}{path}",
        "mime_type": _mime_type(diagnostic),
        "protocol": diagnostic.get("protocol"),
        "container": diagnostic.get("container"),
        "video_codec": diagnostic.get("video_codec"),
        "audio_codec": diagnostic.get("audio_codec"),
        "width": diagnostic.get("width"),
        "height": diagnostic.get("height"),
        "hdr": diagnostic.get("hdr"),
        "audio_channels": diagnostic.get("audio_channels"),
        # Never return provider URLs, cookies, Authorization headers or tokens.
    }


@router.api_route("/api/v1/play/episode/{episode_id}", methods=["GET", "HEAD"])
def play_episode(episode_id: str, request: Request):
    return gateway._play(
        gateway._vod_candidates(episode_id),
        request,
        "Episode stream not found",
        "vod",
    )
