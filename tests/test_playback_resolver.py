from backend.playback_resolver import (
    candidate_diagnostic,
    compatibility_score,
    get_profile,
    infer_traits,
    profile_from_headers,
    rank_candidates,
)
from backend.streaming_gateway import UpstreamCandidate


def c(cid: str, url: str, score: float = 50) -> UpstreamCandidate:
    return UpstreamCandidate(cid, url, score=score)


def test_infer_hls_hevc_and_resolution_hints():
    traits = infer_traits("https://media.example/live/channel.hevc.1080p.m3u8?token=secret")
    assert traits.protocol == "hls"
    assert traits.video_codec == "hevc"
    assert traits.height == 1080
    assert traits.container == "hls"


def test_modern_android_prefers_hevc_when_other_scores_equal():
    profile = get_profile("android-tv-modern")
    avc = c("avc", "https://x/movie.h264.1080p.mp4", 70)
    hevc = c("hevc", "https://x/movie.hevc.1080p.mp4", 70)
    ranked = rank_candidates([avc, hevc], profile, "vod")
    assert ranked[0].id == "hevc"


def test_legacy_android_rejects_known_hevc_candidate():
    profile = get_profile("android-tv-legacy")
    hevc = c("hevc", "https://x/movie.hevc.1080p.mp4", 100)
    avc = c("avc", "https://x/movie.h264.1080p.mp4", 50)
    assert compatibility_score(hevc, profile, "vod") < -9000
    assert rank_candidates([hevc, avc], profile, "vod")[0].id == "avc"


def test_resolution_above_device_limit_is_penalized():
    profile = get_profile("web-tv")
    four_k = c("4k", "https://x/movie.h264.2160p.mp4", 100)
    full_hd = c("fhd", "https://x/movie.h264.1080p.mp4", 80)
    assert rank_candidates([four_k, full_hd], profile, "vod")[0].id == "fhd"


def test_live_prefers_hls_for_same_quality():
    profile = get_profile("generic")
    hls = c("hls", "https://x/live/1080p.m3u8", 60)
    direct = c("direct", "https://x/live/1080p.ts", 60)
    assert rank_candidates([direct, hls], profile, "live")[0].id == "hls"


def test_client_can_report_real_device_capabilities():
    profile = profile_from_headers({
        "x-familystream-device": "android-tv-modern",
        "x-familystream-video-codecs": "h264,avc",
        "x-familystream-max-height": "720",
    })
    assert profile.id == "android-tv-modern"
    assert profile.video_codecs == ("h264", "avc")
    assert profile.max_height == 720


def test_invalid_client_height_cannot_create_unbounded_profile():
    profile = profile_from_headers({
        "x-familystream-device": "web-tv",
        "x-familystream-max-height": "99999",
    })
    assert profile.max_height == 1080


def test_diagnostics_never_expose_upstream_url_headers_or_tokens():
    candidate = UpstreamCandidate(
        "stream-1",
        "https://secret.example/movie.hevc.1080p.m3u8?token=VERY_PRIVATE",
        {"Authorization": "Bearer PRIVATE", "Cookie": "session=PRIVATE"},
        90,
    )
    diagnostic = candidate_diagnostic(candidate, get_profile("android-tv-modern"), "vod")
    text = repr(diagnostic)
    assert "VERY_PRIVATE" not in text
    assert "Bearer PRIVATE" not in text
    assert "session=PRIVATE" not in text
    assert "secret.example" not in text
