from __future__ import annotations

import json
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Iterable

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response, StreamingResponse

from backend.streaming_gateway import (
    UpstreamCandidate,
    is_hls,
    request_headers_for_upstream,
    response_headers_for_client,
    rewrite_hls_manifest,
    upstream_status_usable,
)

router = APIRouter()


@dataclass(slots=True)
class GatewaySession:
    id: str
    headers: dict[str, str]
    expires_at: float
    resources: dict[str, str] = field(default_factory=dict)


class GatewaySessionStore:
    """Opaque, short-lived HLS resource registry.

    Upstream URLs (which may contain provider tokens) never appear in client-facing
    manifests. Clients receive random session/resource identifiers only.
    """

    def __init__(self, ttl_seconds: int = 7200):
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[str, GatewaySession] = {}
        self._lock = threading.RLock()

    def _prune(self) -> None:
        now = time.monotonic()
        expired = [sid for sid, session in self._sessions.items() if session.expires_at <= now]
        for sid in expired:
            self._sessions.pop(sid, None)

    def create(self, headers: dict[str, str] | None = None) -> GatewaySession:
        with self._lock:
            self._prune()
            sid = secrets.token_urlsafe(24)
            session = GatewaySession(
                id=sid,
                headers=dict(headers or {}),
                expires_at=time.monotonic() + self.ttl_seconds,
            )
            self._sessions[sid] = session
            return session

    def get(self, session_id: str) -> GatewaySession | None:
        with self._lock:
            self._prune()
            session = self._sessions.get(session_id)
            if session:
                session.expires_at = time.monotonic() + self.ttl_seconds
            return session

    def register(self, session_id: str, url: str) -> str:
        with self._lock:
            session = self.get(session_id)
            if session is None:
                raise KeyError(session_id)
            rid = secrets.token_urlsafe(24)
            session.resources[rid] = url
            return rid

    def resolve(self, session_id: str, resource_id: str) -> tuple[GatewaySession, str] | None:
        with self._lock:
            session = self.get(session_id)
            if session is None:
                return None
            url = session.resources.get(resource_id)
            if url is None:
                return None
            return session, url


SESSIONS = GatewaySessionStore()
STREAM_TIMEOUT = httpx.Timeout(connect=8.0, read=None, write=30.0, pool=8.0)
PROBE_TIMEOUT = httpx.Timeout(8.0)
MAX_MANIFEST_BYTES = 4 * 1024 * 1024


def _db_execute(sql: str, params: tuple = (), fetch: bool = False):
    # Imported lazily to avoid an import cycle while backend.app_v03 swaps routes.
    from backend.app import db_execute

    return db_execute(sql, params, fetch)


def _safe_url(url: str) -> bool:
    from backend.app import safe_url

    return safe_url(url)


def _live_candidates(channel_id: str) -> list[UpstreamCandidate]:
    rows = _db_execute(
        "SELECT id,url,referrer,user_agent,score FROM streams "
        "WHERE channel_id=? AND status IN ('healthy','degraded') "
        "ORDER BY primary_stream DESC,score DESC",
        (channel_id,),
        True,
    )
    result: list[UpstreamCandidate] = []
    for sid, url, referrer, user_agent, score in rows:
        headers: dict[str, str] = {}
        if user_agent:
            headers["User-Agent"] = user_agent
        if referrer:
            headers["Referer"] = referrer
        result.append(UpstreamCandidate(sid, url, headers, float(score or 0)))
    return result


def _vod_candidates(vod_id: str) -> list[UpstreamCandidate]:
    rows = _db_execute(
        "SELECT id,url,headers_json,score FROM vod_streams "
        "WHERE item_id=? ORDER BY is_primary DESC,score DESC",
        (vod_id,),
        True,
    )
    result: list[UpstreamCandidate] = []
    for sid, url, headers_json, score in rows:
        try:
            headers = json.loads(headers_json or "{}")
            if not isinstance(headers, dict):
                headers = {}
        except (TypeError, ValueError, json.JSONDecodeError):
            headers = {}
        result.append(UpstreamCandidate(sid, url, {str(k): str(v) for k, v in headers.items()}, float(score or 0)))
    return result


def _probe(candidate: UpstreamCandidate) -> int | None:
    if not _safe_url(candidate.url):
        return None
    try:
        with httpx.Client(timeout=PROBE_TIMEOUT, follow_redirects=True) as client:
            response = client.head(candidate.url, headers=candidate.headers)
            if upstream_status_usable(response.status_code):
                return response.status_code
            # A number of media origins reject HEAD while serving GET correctly.
            if response.status_code in {400, 403, 405, 501}:
                headers = dict(candidate.headers)
                headers["Range"] = "bytes=0-0"
                with client.stream("GET", candidate.url, headers=headers) as get_response:
                    return get_response.status_code
            return response.status_code
    except httpx.HTTPError:
        return None


def _select(candidates: Iterable[UpstreamCandidate]) -> UpstreamCandidate | None:
    for candidate in candidates:
        status = _probe(candidate)
        if status is not None and upstream_status_usable(status):
            return candidate
    return None


def _client_base(request: Request) -> str:
    configured = request.app.state.gateway_public_base if hasattr(request.app.state, "gateway_public_base") else None
    return (configured or str(request.base_url).rstrip("/"))


def _proxy_resource_url(request: Request, session_id: str, absolute_url: str) -> str:
    if not _safe_url(absolute_url):
        raise HTTPException(502, "Unsafe HLS resource URL")
    rid = SESSIONS.register(session_id, absolute_url)
    return f"{_client_base(request)}/api/v1/gateway/hls/{session_id}/{rid}"


def _stream_response(candidate: UpstreamCandidate, request: Request):
    upstream_headers = request_headers_for_upstream(candidate.headers, request.headers)
    client = httpx.Client(timeout=STREAM_TIMEOUT, follow_redirects=True)
    try:
        upstream_request = client.build_request(request.method, candidate.url, headers=upstream_headers)
        response = client.send(upstream_request, stream=True)
    except httpx.HTTPError as exc:
        client.close()
        raise HTTPException(502, f"Upstream media request failed: {type(exc).__name__}") from exc

    if not upstream_status_usable(response.status_code):
        status = response.status_code
        response.close()
        client.close()
        raise HTTPException(502, f"Upstream media rejected request ({status})")

    outgoing_headers = response_headers_for_client(response.headers)

    if request.method == "HEAD":
        response.close()
        client.close()
        return PlainTextResponse("", status_code=response.status_code, headers=outgoing_headers)

    content_type = response.headers.get("content-type")
    if is_hls(content_type, candidate.url):
        try:
            payload = response.read(MAX_MANIFEST_BYTES + 1)
        finally:
            response.close()
            client.close()
        if len(payload) > MAX_MANIFEST_BYTES:
            raise HTTPException(502, "HLS manifest exceeds gateway limit")
        manifest = payload.decode("utf-8", errors="replace")
        session = SESSIONS.create(candidate.headers)
        rewritten = rewrite_hls_manifest(
            manifest,
            candidate.url,
            lambda url: _proxy_resource_url(request, session.id, url),
        )
        outgoing_headers.pop("Content-Length", None)
        outgoing_headers.pop("content-length", None)
        outgoing_headers["Cache-Control"] = "no-store"
        return Response(
            rewritten,
            status_code=response.status_code,
            media_type="application/vnd.apple.mpegurl",
            headers=outgoing_headers,
        )

    def body():
        try:
            for chunk in response.iter_bytes(256 * 1024):
                yield chunk
        finally:
            response.close()
            client.close()

    return StreamingResponse(
        body(),
        status_code=response.status_code,
        media_type=content_type,
        headers=outgoing_headers,
    )


def _play(candidates: list[UpstreamCandidate], request: Request, not_found: str):
    if not candidates:
        raise HTTPException(404, not_found)
    selected = _select(candidates)
    if selected is None:
        raise HTTPException(502, "No usable upstream media source")
    return _stream_response(selected, request)


@router.api_route("/api/v1/play/live/{channel_id}", methods=["GET", "HEAD"])
def play_live(channel_id: str, request: Request):
    return _play(_live_candidates(channel_id), request, "Live channel not found")


@router.api_route("/api/v1/play/vod/{vod_id}", methods=["GET", "HEAD"])
def play_vod(vod_id: str, request: Request):
    return _play(_vod_candidates(vod_id), request, "VOD item not found")


# Compatibility routes: app_v03 removes the legacy v0.2 handlers before this
# router is included, so existing M3U/STRM URLs keep working with the new engine.
@router.api_route("/live/stream/{channel_id}", methods=["GET", "HEAD"])
def play_live_compat(channel_id: str, request: Request):
    return play_live(channel_id, request)


@router.api_route("/vod/stream/{vod_id}", methods=["GET", "HEAD"])
def play_vod_compat(vod_id: str, request: Request):
    return play_vod(vod_id, request)


@router.api_route("/api/v1/gateway/hls/{session_id}/{resource_id}", methods=["GET", "HEAD"])
def hls_resource(session_id: str, resource_id: str, request: Request):
    resolved = SESSIONS.resolve(session_id, resource_id)
    if resolved is None:
        raise HTTPException(404, "Expired or unknown gateway resource")
    session, url = resolved
    if not _safe_url(url):
        raise HTTPException(502, "Unsafe HLS resource URL")

    candidate = UpstreamCandidate(resource_id, url, session.headers)
    upstream_headers = request_headers_for_upstream(session.headers, request.headers)
    client = httpx.Client(timeout=STREAM_TIMEOUT, follow_redirects=True)
    try:
        upstream_request = client.build_request(request.method, url, headers=upstream_headers)
        response = client.send(upstream_request, stream=True)
    except httpx.HTTPError as exc:
        client.close()
        raise HTTPException(502, f"HLS resource request failed: {type(exc).__name__}") from exc

    if not upstream_status_usable(response.status_code):
        status = response.status_code
        response.close()
        client.close()
        raise HTTPException(502, f"HLS resource rejected request ({status})")

    outgoing_headers = response_headers_for_client(response.headers)
    if request.method == "HEAD":
        response.close()
        client.close()
        return PlainTextResponse("", status_code=response.status_code, headers=outgoing_headers)

    content_type = response.headers.get("content-type")
    if is_hls(content_type, url):
        try:
            payload = response.read(MAX_MANIFEST_BYTES + 1)
        finally:
            response.close()
            client.close()
        if len(payload) > MAX_MANIFEST_BYTES:
            raise HTTPException(502, "HLS manifest exceeds gateway limit")
        manifest = payload.decode("utf-8", errors="replace")
        rewritten = rewrite_hls_manifest(
            manifest,
            url,
            lambda child_url: _proxy_resource_url(request, session_id, child_url),
        )
        outgoing_headers.pop("Content-Length", None)
        outgoing_headers.pop("content-length", None)
        outgoing_headers["Cache-Control"] = "no-store"
        return Response(
            rewritten,
            status_code=response.status_code,
            media_type="application/vnd.apple.mpegurl",
            headers=outgoing_headers,
        )

    def body():
        try:
            for chunk in response.iter_bytes(256 * 1024):
                yield chunk
        finally:
            response.close()
            client.close()

    return StreamingResponse(
        body(),
        status_code=response.status_code,
        media_type=content_type,
        headers=outgoing_headers,
    )
