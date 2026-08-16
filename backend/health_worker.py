from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from backend.health_engine import record_source_result
from backend.streaming_gateway import UpstreamCandidate, upstream_status_usable


@dataclass(frozen=True, slots=True)
class HealthCheckResult:
    stream_id: str
    item_kind: str
    success: bool
    http_status: int | None
    latency_ms: float | None
    error_code: str | None = None


def _db_execute(sql: str, params: tuple = (), fetch: bool = False):
    from backend.app import db_execute
    return db_execute(sql, params, fetch)


def _safe_url(url: str) -> bool:
    from backend.app import safe_url
    return safe_url(url)


def _live_due(limit: int) -> list[UpstreamCandidate]:
    rows = _db_execute(
        "SELECT s.id,s.url,s.referrer,s.user_agent,s.score FROM streams s "
        "LEFT JOIN playback_source_state h ON h.stream_id=s.id AND h.item_kind='live' "
        "ORDER BY CASE WHEN h.updated_at IS NULL THEN 0 ELSE 1 END, h.updated_at ASC, s.score DESC LIMIT ?",
        (limit,), True,
    )
    result = []
    for sid, url, referrer, user_agent, score in rows:
        headers: dict[str, str] = {}
        if user_agent: headers["User-Agent"] = user_agent
        if referrer: headers["Referer"] = referrer
        result.append(UpstreamCandidate(sid, url, headers, float(score or 0)))
    return result


def _vod_due(limit: int) -> list[UpstreamCandidate]:
    rows = _db_execute(
        "SELECT s.id,s.url,s.headers_json,s.score FROM vod_streams s "
        "LEFT JOIN playback_source_state h ON h.stream_id=s.id AND h.item_kind='vod' "
        "ORDER BY CASE WHEN h.updated_at IS NULL THEN 0 ELSE 1 END, h.updated_at ASC, s.score DESC LIMIT ?",
        (limit,), True,
    )
    result = []
    for sid, url, headers_json, score in rows:
        try:
            raw = json.loads(headers_json or "{}")
            headers = raw if isinstance(raw, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            headers = {}
        result.append(UpstreamCandidate(sid, url, {str(k): str(v) for k, v in headers.items()}, float(score or 0)))
    return result


def check_candidate(candidate: UpstreamCandidate, item_kind: str, timeout_seconds: float = 8.0) -> HealthCheckResult:
    if not _safe_url(candidate.url):
        return HealthCheckResult(candidate.id, item_kind, False, None, None, "unsafe_url")
    started = time.monotonic()
    try:
        # Use the same bounded media-aware probe as the playback resolver.
        # This avoids publishing endpoints that merely return HTTP 200 with HTML,
        # geo-block pages or extensionless manifests the player cannot classify.
        from backend.gateway_runtime import _probe_media

        probe = _probe_media(candidate)
        latency = round((time.monotonic() - started) * 1000.0, 2)
        success = (
            probe.status_code is not None
            and upstream_status_usable(probe.status_code)
            and probe.mime_type is not None
        )
        error = None if success else (
            f"http_{probe.status_code}" if probe.status_code is not None else "not_media"
        )
        return HealthCheckResult(candidate.id, item_kind, success, probe.status_code, latency, error)
    except httpx.TimeoutException:
        return HealthCheckResult(candidate.id, item_kind, False, None, round((time.monotonic() - started) * 1000.0, 2), "timeout")
    except httpx.HTTPError as exc:
        return HealthCheckResult(candidate.id, item_kind, False, None, round((time.monotonic() - started) * 1000.0, 2), type(exc).__name__)


def _persist(result: HealthCheckResult) -> None:
    record_source_result(
        _db_execute,
        result.stream_id,
        result.item_kind,
        success=result.success,
        http_status=result.http_status,
        latency_ms=result.latency_ms,
        error_code=result.error_code,
    )
    status = "healthy" if result.success else "offline"
    checked_at = datetime.now(timezone.utc).isoformat()
    success_int = int(result.success)
    if result.item_kind == "live":
        _db_execute(
            "UPDATE streams SET status=?,last_checked=?,last_success=CASE WHEN ?=1 THEN ? ELSE last_success END,"
            "failure_count=CASE WHEN ?=1 THEN 0 ELSE failure_count+1 END WHERE id=?",
            (status, checked_at, success_int, checked_at, success_int, result.stream_id),
        )
    else:
        _db_execute(
            "UPDATE vod_streams SET status=?,last_checked=?,last_success=CASE WHEN ?=1 THEN ? ELSE last_success END,"
            "failure_count=CASE WHEN ?=1 THEN 0 ELSE failure_count+1 END WHERE id=?",
            (status, checked_at, success_int, checked_at, success_int, result.stream_id),
        )


def _refresh_publication() -> None:
    from backend.app import MIN_SCORE, export_files

    _db_execute(
        "UPDATE channels SET published=CASE WHEN id IN ("
        "SELECT channel_id FROM streams WHERE status IN ('healthy','degraded') AND score>=? GROUP BY channel_id"
        ") THEN 1 ELSE 0 END",
        (MIN_SCORE,),
    )
    export_files()


def _check_group(kind: str, candidates: list[UpstreamCandidate]) -> list[HealthCheckResult]:
    if not candidates:
        return []
    workers = max(1, min(12, len(candidates)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda candidate: check_candidate(candidate, kind), candidates))


def run_health_batch(live_limit: int = 20, vod_limit: int = 10) -> dict[str, Any]:
    results: list[HealthCheckResult] = []
    for kind, candidates in (("live", _live_due(live_limit)), ("vod", _vod_due(vod_limit))):
        checked = _check_group(kind, candidates)
        for result in checked:
            _persist(result)
        results.extend(checked)
    _refresh_publication()
    successes = sum(1 for item in results if item.success)
    return {
        "checked": len(results),
        "healthy": successes,
        "failed": len(results) - successes,
        "live_checked": sum(1 for item in results if item.item_kind == "live"),
        "vod_checked": sum(1 for item in results if item.item_kind == "vod"),
    }
