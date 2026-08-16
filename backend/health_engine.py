from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping


@dataclass(frozen=True, slots=True)
class SourceHealth:
    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0
    ewma_latency_ms: float | None = None
    last_http_status: int | None = None
    last_result: str | None = None
    last_error_code: str | None = None
    quarantine_until: str | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def quarantine_seconds(consecutive_failures: int) -> int:
    """Short circuit-breaker backoff; capped so recovered sources re-enter rotation."""
    if consecutive_failures < 3:
        return 0
    return min(1800, 15 * (2 ** min(consecutive_failures - 3, 7)))


def health_score_adjustment(health: Mapping[str, object] | None, now: datetime | None = None) -> float:
    if not health:
        return 0.0
    now = now or utcnow()
    failures = int(health.get("consecutive_failures") or 0)
    success_count = int(health.get("success_count") or 0)
    failure_count = int(health.get("failure_count") or 0)
    latency = health.get("ewma_latency_ms")
    quarantine = parse_time(str(health.get("quarantine_until") or ""))

    if quarantine and quarantine > now:
        return -100000.0

    value = 0.0
    if failures:
        value -= min(180.0, failures * 32.0)
    total = success_count + failure_count
    if total:
        success_ratio = success_count / total
        value += (success_ratio - 0.5) * 40.0
    try:
        latency_value = float(latency) if latency is not None else None
    except (TypeError, ValueError):
        latency_value = None
    if latency_value is not None:
        # Reward fast starts, gently penalize slow starts without swamping codec compatibility.
        value += max(-35.0, min(18.0, (1800.0 - latency_value) / 100.0))
    return value


def update_health_values(
    previous: Mapping[str, object] | None,
    *,
    success: bool,
    http_status: int | None = None,
    latency_ms: float | None = None,
    error_code: str | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    now = now or utcnow()
    previous = previous or {}
    successes = int(previous.get("success_count") or 0) + (1 if success else 0)
    failures = int(previous.get("failure_count") or 0) + (0 if success else 1)
    consecutive = 0 if success else int(previous.get("consecutive_failures") or 0) + 1

    old_latency = previous.get("ewma_latency_ms")
    try:
        old_latency_f = float(old_latency) if old_latency is not None else None
    except (TypeError, ValueError):
        old_latency_f = None
    if latency_ms is None:
        ewma = old_latency_f
    elif old_latency_f is None:
        ewma = float(latency_ms)
    else:
        ewma = round(old_latency_f * 0.7 + float(latency_ms) * 0.3, 2)

    backoff = quarantine_seconds(consecutive)
    quarantine_until = (now + timedelta(seconds=backoff)).isoformat() if backoff else None
    return {
        "success_count": successes,
        "failure_count": failures,
        "consecutive_failures": consecutive,
        "ewma_latency_ms": ewma,
        "last_http_status": http_status,
        "last_result": "success" if success else "failure",
        "last_error_code": None if success else (error_code or "unknown"),
        "last_success": now.isoformat() if success else previous.get("last_success"),
        "last_failure": previous.get("last_failure") if success else now.isoformat(),
        "quarantine_until": quarantine_until,
        "updated_at": now.isoformat(),
    }


def load_health(db_execute: Callable[..., Any], stream_id: str, item_kind: str) -> dict[str, object] | None:
    rows = db_execute(
        "SELECT success_count,failure_count,consecutive_failures,ewma_latency_ms,last_http_status,last_result,last_error_code,last_success,last_failure,quarantine_until,updated_at "
        "FROM playback_source_state WHERE stream_id=? AND item_kind=?",
        (stream_id, item_kind),
        True,
    )
    if not rows:
        return None
    keys = [
        "success_count", "failure_count", "consecutive_failures", "ewma_latency_ms",
        "last_http_status", "last_result", "last_error_code", "last_success",
        "last_failure", "quarantine_until", "updated_at",
    ]
    return dict(zip(keys, rows[0]))


def record_source_result(
    db_execute: Callable[..., Any],
    stream_id: str,
    item_kind: str,
    *,
    success: bool,
    http_status: int | None = None,
    latency_ms: float | None = None,
    error_code: str | None = None,
) -> dict[str, object]:
    if item_kind not in {"live", "vod"}:
        raise ValueError("item_kind must be live or vod")
    previous = load_health(db_execute, stream_id, item_kind)
    values = update_health_values(
        previous,
        success=success,
        http_status=http_status,
        latency_ms=latency_ms,
        error_code=error_code,
    )
    db_execute(
        "INSERT INTO playback_source_state(stream_id,item_kind,success_count,failure_count,consecutive_failures,ewma_latency_ms,last_http_status,last_result,last_error_code,last_success,last_failure,quarantine_until,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(stream_id,item_kind) DO UPDATE SET "
        "success_count=excluded.success_count,failure_count=excluded.failure_count,consecutive_failures=excluded.consecutive_failures,"
        "ewma_latency_ms=excluded.ewma_latency_ms,last_http_status=excluded.last_http_status,last_result=excluded.last_result,"
        "last_error_code=excluded.last_error_code,last_success=excluded.last_success,last_failure=excluded.last_failure,"
        "quarantine_until=excluded.quarantine_until,updated_at=excluded.updated_at",
        (
            stream_id, item_kind, values["success_count"], values["failure_count"],
            values["consecutive_failures"], values["ewma_latency_ms"], values["last_http_status"],
            values["last_result"], values["last_error_code"], values["last_success"],
            values["last_failure"], values["quarantine_until"], values["updated_at"],
        ),
    )
    return values
