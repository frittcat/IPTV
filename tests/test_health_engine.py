from datetime import datetime, timedelta, timezone

from backend.health_engine import (
    health_score_adjustment,
    quarantine_seconds,
    update_health_values,
)
from backend.playback_resolver import get_profile, rank_candidates
from backend.streaming_gateway import UpstreamCandidate


def test_circuit_breaker_starts_after_three_consecutive_failures():
    assert quarantine_seconds(0) == 0
    assert quarantine_seconds(2) == 0
    assert quarantine_seconds(3) == 15
    assert quarantine_seconds(4) == 30
    assert quarantine_seconds(20) <= 1800


def test_success_resets_consecutive_failures_and_keeps_history():
    previous = {
        "success_count": 2,
        "failure_count": 4,
        "consecutive_failures": 4,
        "ewma_latency_ms": 1000,
    }
    values = update_health_values(previous, success=True, http_status=200, latency_ms=500)
    assert values["success_count"] == 3
    assert values["failure_count"] == 4
    assert values["consecutive_failures"] == 0
    assert values["quarantine_until"] is None
    assert values["ewma_latency_ms"] == 850.0


def test_quarantined_source_gets_hard_penalty():
    now = datetime.now(timezone.utc)
    health = {
        "consecutive_failures": 3,
        "success_count": 10,
        "failure_count": 3,
        "quarantine_until": (now + timedelta(minutes=5)).isoformat(),
    }
    assert health_score_adjustment(health, now=now) < -90000


def test_resolver_prefers_stable_source_over_slightly_higher_base_score():
    profile = get_profile("android-tv-modern")
    flaky = UpstreamCandidate("flaky", "https://x/movie.hevc.1080p.mp4", score=90)
    stable = UpstreamCandidate("stable", "https://x/movie.hevc.1080p.mp4", score=80)
    health = {
        "flaky": {"success_count": 1, "failure_count": 8, "consecutive_failures": 2, "ewma_latency_ms": 4000},
        "stable": {"success_count": 20, "failure_count": 1, "consecutive_failures": 0, "ewma_latency_ms": 300},
    }
    ranked = rank_candidates([flaky, stable], profile, "vod", health_profiles=health)
    assert ranked[0].id == "stable"


def test_health_does_not_override_known_codec_incompatibility():
    profile = get_profile("android-tv-legacy")
    incompatible = UpstreamCandidate("hevc", "https://x/movie.hevc.1080p.mp4", score=100)
    compatible = UpstreamCandidate("h264", "https://x/movie.h264.1080p.mp4", score=10)
    health = {
        "hevc": {"success_count": 100, "failure_count": 0, "consecutive_failures": 0},
        "h264": {"success_count": 1, "failure_count": 0, "consecutive_failures": 0},
    }
    assert rank_candidates([incompatible, compatible], profile, "vod", health_profiles=health)[0].id == "h264"
