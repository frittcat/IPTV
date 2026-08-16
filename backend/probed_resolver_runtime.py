from __future__ import annotations

import backend.gateway_runtime as gateway_runtime
from backend.playback_resolver import (
    candidate_diagnostic as base_candidate_diagnostic,
    rank_candidates as base_rank_candidates,
)
from backend.streaming_gateway import UpstreamCandidate


def _db_execute(sql: str, params: tuple = (), fetch: bool = False):
    from backend.app import db_execute
    return db_execute(sql, params, fetch)


def technical_profiles(candidates: list[UpstreamCandidate], kind: str) -> dict[str, dict[str, object]]:
    if not candidates:
        return {}
    ids = [candidate.id for candidate in candidates]
    placeholders = ",".join("?" for _ in ids)
    rows = _db_execute(
        "SELECT stream_id,protocol,container,video_codec,audio_codec,width,height,bitrate,fps,hdr,audio_channels,probe_status "
        f"FROM stream_technical_profiles WHERE item_kind=? AND stream_id IN ({placeholders})",
        (kind, *ids),
        True,
    )
    keys = [
        "protocol", "container", "video_codec", "audio_codec", "width", "height",
        "bitrate", "fps", "hdr", "audio_channels", "probe_status",
    ]
    return {row[0]: dict(zip(keys, row[1:])) for row in rows}


def health_profiles(candidates: list[UpstreamCandidate], kind: str) -> dict[str, dict[str, object]]:
    if not candidates:
        return {}
    ids = [candidate.id for candidate in candidates]
    placeholders = ",".join("?" for _ in ids)
    rows = _db_execute(
        "SELECT stream_id,success_count,failure_count,consecutive_failures,ewma_latency_ms,last_http_status,last_result,last_error_code,last_success,last_failure,quarantine_until,updated_at "
        f"FROM playback_source_state WHERE item_kind=? AND stream_id IN ({placeholders})",
        (kind, *ids),
        True,
    )
    keys = [
        "success_count", "failure_count", "consecutive_failures", "ewma_latency_ms",
        "last_http_status", "last_result", "last_error_code", "last_success",
        "last_failure", "quarantine_until", "updated_at",
    ]
    return {row[0]: dict(zip(keys, row[1:])) for row in rows}


def rank_candidates(candidates, profile, kind):
    measured = technical_profiles(candidates, kind)
    health = health_profiles(candidates, kind)
    return base_rank_candidates(candidates, profile, kind, measured, health)


def candidate_diagnostic(candidate, profile, kind):
    measured = technical_profiles([candidate], kind).get(candidate.id)
    health = health_profiles([candidate], kind).get(candidate.id)
    return base_candidate_diagnostic(candidate, profile, kind, measured, health)


def activate() -> None:
    # gateway_runtime resolves these globals at request time. The existing routes
    # therefore gain measured codec/resolution plus adaptive health ordering.
    gateway_runtime.rank_candidates = rank_candidates
    gateway_runtime.candidate_diagnostic = candidate_diagnostic
