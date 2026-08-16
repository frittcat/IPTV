from backend.playback_resolver import (
    candidate_diagnostic,
    compatibility_score,
    get_profile,
    measured_traits,
    rank_candidates,
)
from backend.streaming_gateway import UpstreamCandidate


def test_measured_hevc_overrides_misleading_h264_url_hint():
    legacy = get_profile("android-tv-legacy")
    candidate = UpstreamCandidate(
        "measured-hevc",
        "https://media.example/movie.h264.1080p.mp4",
        score=100,
    )
    technical = {
        "probe_status": "ok",
        "protocol": "direct",
        "container": "mp4",
        "video_codec": "hevc",
        "audio_codec": "aac",
        "width": 1920,
        "height": 1080,
        "bitrate": 4000000,
        "fps": 25.0,
    }
    traits = measured_traits(technical)
    assert traits is not None
    assert traits.source == "probe"
    assert traits.video_codec == "hevc"
    assert compatibility_score(candidate, legacy, "vod", traits) < -9000


def test_rank_uses_probe_database_values_before_url_hints():
    profile = get_profile("android-tv-legacy")
    misleading = UpstreamCandidate("a", "https://x/a.h264.1080p.mp4", score=100)
    compatible = UpstreamCandidate("b", "https://x/b.hevc.1080p.mp4", score=60)
    measured = {
        "a": {
            "probe_status": "ok",
            "protocol": "direct",
            "container": "mp4",
            "video_codec": "hevc",
            "audio_codec": "aac",
            "height": 1080,
        },
        "b": {
            "probe_status": "ok",
            "protocol": "direct",
            "container": "mp4",
            "video_codec": "h264",
            "audio_codec": "aac",
            "height": 1080,
        },
    }
    ranked = rank_candidates([misleading, compatible], profile, "vod", measured)
    assert ranked[0].id == "b"


def test_diagnostic_reports_probe_source_without_upstream_url():
    candidate = UpstreamCandidate(
        "s1",
        "https://secret.example/video.m3u8?token=PRIVATE",
        {"Authorization": "Bearer PRIVATE"},
        80,
    )
    technical = {
        "probe_status": "ok",
        "protocol": "hls",
        "container": "hls",
        "video_codec": "hevc",
        "audio_codec": "eac3",
        "width": 1920,
        "height": 1080,
        "bitrate": 5000000,
        "fps": 25.0,
        "hdr": None,
        "audio_channels": 6,
    }
    diagnostic = candidate_diagnostic(candidate, get_profile("android-tv-modern"), "vod", technical)
    assert diagnostic["traits_source"] == "probe"
    assert diagnostic["video_codec"] == "hevc"
    assert diagnostic["audio_channels"] == 6.0
    text = repr(diagnostic)
    assert "secret.example" not in text
    assert "PRIVATE" not in text
