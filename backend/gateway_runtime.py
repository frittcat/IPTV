from __future__ import annotations

import json
import secrets
import threading
import time
from dataclasses import dataclass, field

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response, StreamingResponse

from backend.playback_resolver import (
    PROFILES,
    candidate_diagnostic,
    profile_from_headers,
    rank_candidates,
)
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
    profile_id: str = "generic"
    resources: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MediaProbeInfo:
    status_code: int | None
    content_type: str | None = None
    mime_type: str | None = None
    protocol: str | None = None
    container: str | None = None


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

    def create(self, headers: dict[str, str] | None = None, profile_id: str = "generic") -> GatewaySession:
        with self._lock:
            self._prune()
            sid = secrets.token_urlsafe(24)
            session = GatewaySession(
                id=sid,
                headers=dict(headers or {}),
                expires_at=time.monotonic() + self.ttl_seconds,
                profile_id=profile_id,
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
PROBE_PREFIX_BYTES = 64 * 1024


def _db_execute(sql: str, params: tuple = (), fetch: bool = False):
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


def _ts_prefix(prefix: bytes) -> bool:
    if len(prefix) < 188:
        return False
    for start in range(min(188, len(prefix))):
        if prefix[start] != 0x47:
            continue
        matches = 1
        for step in (188, 376, 564):
            pos = start + step
            if pos >= len(prefix):
                break
            if prefix[pos] == 0x47:
                matches += 1
            else:
                break
        if matches >= 2:
            return True
    return False


def _sniff_media(content_type: str | None, url: str, prefix: bytes = b"") -> tuple[str | None, str | None, str | None]:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    text_prefix = prefix[:4096].decode("utf-8", errors="ignore") if prefix else ""

    if is_hls(content_type, url, text_prefix):
        return "application/x-mpegURL", "hls", "hls"
    if media_type in {"video/mp4", "application/mp4"} or (len(prefix) >= 12 and b"ftyp" in prefix[:32]):
        return "video/mp4", "direct", "mp4"
    if media_type in {"video/mp2t", "video/mpegts", "application/vnd.apple.mpegurl.audio"} or _ts_prefix(prefix):
        return "video/mp2t", "direct", "mpegts"
    if media_type in {"video/x-matroska", "application/x-matroska"} or prefix.startswith(b"\x1aE\xdf\xa3"):
        return "video/x-matroska", "direct", "matroska"
    if media_type.startswith("video/") or media_type.startswith("audio/"):
        return media_type, "direct", None
    return None, None, None


def _probe_media(candidate: UpstreamCandidate) -> MediaProbeInfo:
    """Validate that an upstream is not just HTTP-200 but actual media.

    IPTV endpoints frequently answer HEAD with 200 while GET returns an HTML page,
    geo-block message, or an extensionless HLS manifest. We therefore use HEAD as
    a cheap hint and perform a bounded GET when the format is not already certain.
    """
    if not _safe_url(candidate.url):
        return MediaProbeInfo(None)

    try:
        with httpx.Client(timeout=PROBE_TIMEOUT, follow_redirects=True) as client:
            head_status: int | None = None
            head_content_type: str | None = None
            try:
                head = client.head(candidate.url, headers=candidate.headers)
                head_status = head.status_code
                head_content_type = head.headers.get("content-type")
                if upstream_status_usable(head_status):
                    mime, protocol, container = _sniff_media(head_content_type, candidate.url)
                    if mime is not None:
                        return MediaProbeInfo(head_status, head_content_type, mime, protocol, container)
            except httpx.HTTPError:
                pass

            headers = dict(candidate.headers)
            headers["Range"] = f"bytes=0-{PROBE_PREFIX_BYTES - 1}"
            with client.stream("GET", candidate.url, headers=headers) as response:
                status = response.status_code
                content_type = response.headers.get("content-type") or head_content_type
                if not upstream_status_usable(status):
                    return MediaProbeInfo(status, content_type)
                prefix = next(response.iter_bytes(PROBE_PREFIX_BYTES), b"")
                mime, protocol, container = _sniff_media(content_type, candidate.url, prefix)
                return MediaProbeInfo(status, content_type, mime, protocol, container)
    except httpx.HTTPError:
        return MediaProbeInfo(None)


def _probe(candidate: UpstreamCandidate) -> int | None:
    return _probe_media(candidate).status_code


def _client_base(request: Request) -> str:
    configured = request.app.state.gateway_public_base if hasattr(request.app.state, "gateway_public_base") else None
    return configured or str(request.base_url).rstrip("/")


def _proxy_resource_url(request: Request, session_id: str, absolute_url: str) -> str:
    if not _safe_url(absolute_url):
        raise HTTPException(502, "Unsafe HLS resource URL")
    rid = SESSIONS.register(session_id, absolute_url)
    return f"{_client_base(request)}/api/v1/gateway/hls/{session_id}/{rid}"


def _stream_response(candidate: UpstreamCandidate, request: Request, profile_id: str = "generic"):
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
    outgoing_headers["X-GaloDoidoTV-Device-Profile"] = profile_id

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
        session = SESSIONS.create(candidate.headers, profile_id=profile_id)
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

    # Some IPTV origins serve extensionless HLS with application/octet-stream or
    # text/plain. Sniff a bounded prefix before deciding to relay it as a direct
    # byte stream so Android TV receives a real HLS manifest from the gateway.
    if not is_hls(content_type, candidate.url):
        try:
            first = next(response.iter_bytes(PROBE_PREFIX_BYTES), b"")
        except httpx.HTTPError:
            first = b""
        mime, protocol, _container = _sniff_media(content_type, candidate.url, first)
        if protocol == "hls":
            try:
                remainder = b"".join(response.iter_bytes())
                payload = first + remainder
            finally:
                response.close()
                client.close()
            if len(payload) > MAX_MANIFEST_BYTES:
                raise HTTPException(502, "HLS manifest exceeds gateway limit")
            manifest = payload.decode("utf-8", errors="replace")
            session = SESSIONS.create(candidate.headers, profile_id=profile_id)
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

        def body_with_prefix():
            try:
                if first:
                    yield first
                for chunk in response.iter_bytes(256 * 1024):
                    yield chunk
            finally:
                response.close()
                client.close()

        return StreamingResponse(
            body_with_prefix(),
            status_code=response.status_code,
            media_type=mime or content_type,
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


def _play(candidates: list[UpstreamCandidate], request: Request, not_found: str, kind: str):
    if not candidates:
        raise HTTPException(404, not_found)

    profile = profile_from_headers(request.headers)
    ranked = rank_candidates(candidates, profile, kind)
    attempted = 0

    for candidate in ranked:
        probe = _probe_media(candidate)
        if probe.status_code is None or not upstream_status_usable(probe.status_code) or probe.mime_type is None:
            continue
        attempted += 1
        try:
            return _stream_response(candidate, request, profile.id)
        except HTTPException as exc:
            if exc.status_code != 502:
                raise
            continue

    raise HTTPException(502, f"No usable upstream media source after {attempted} playback attempts")


@router.get("/api/v1/playback/profiles")
def playback_profiles():
    return {
        "profiles": [
            {
                "id": profile.id,
                "video_codecs": list(profile.video_codecs),
                "audio_codecs": list(profile.audio_codecs),
                "max_height": profile.max_height,
                "preferred_protocols": list(profile.preferred_protocols),
                "prefer_hevc": profile.prefer_hevc,
            }
            for profile in PROFILES.values()
        ]
    }


@router.get("/api/v1/playback/diagnostics/{kind}/{item_id}")
def playback_diagnostics(kind: str, item_id: str, request: Request):
    if kind not in {"live", "vod"}:
        raise HTTPException(400, "kind must be live or vod")
    candidates = _live_candidates(item_id) if kind == "live" else _vod_candidates(item_id)
    profile = profile_from_headers(request.headers)
    ranked = rank_candidates(candidates, profile, kind)
    diagnostics = []
    for candidate in ranked:
        item = candidate_diagnostic(candidate, profile, kind)
        probe = _probe_media(candidate)
        item.update({
            "http_status": probe.status_code,
            "detected_mime_type": probe.mime_type,
            "detected_protocol": probe.protocol,
            "detected_container": probe.container,
        })
        diagnostics.append(item)
    return {
        "kind": kind,
        "item_id": item_id,
        "profile": profile.id,
        "candidate_count": len(ranked),
        "candidates": diagnostics,
    }


@router.api_route("/api/v1/play/live/{channel_id}", methods=["GET", "HEAD"])
def play_live(channel_id: str, request: Request):
    return _play(_live_candidates(channel_id), request, "Live channel not found", "live")


@router.api_route("/api/v1/play/vod/{vod_id}", methods=["GET", "HEAD"])
def play_vod(vod_id: str, request: Request):
    return _play(_vod_candidates(vod_id), request, "VOD item not found", "vod")


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
    outgoing_headers["X-GaloDoidoTV-Device-Profile"] = session.profile_id
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
