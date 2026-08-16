from types import SimpleNamespace

import backend.content_runtime as content
import backend.playback_api_runtime as playback_api
from backend.streaming_gateway import UpstreamCandidate


def test_home_feed_returns_live_movies_and_series_without_upstream_urls(monkeypatch):
    monkeypatch.setattr(content, "_live_rows", lambda limit, offset=0, q="", country="", category="": [
        ("ch1", "Canal 1", "FR", '["general"]', "https://img.example/ch1.png", 1),
    ])
    monkeypatch.setattr(content, "_movie_rows", lambda limit, offset=0, q="": [
        ("m1", "Filme 1", 2026, "Plot", "https://img.example/m1.jpg", None, 8.1, 1),
    ])
    monkeypatch.setattr(content, "_series_rows", lambda limit, offset=0, q="": [
        ("s1", "Série 1", 2026, "Plot", "https://img.example/s1.jpg", None, None, 1),
    ])

    payload = content.home(limit=12)
    assert payload["live"][0]["id"] == "ch1"
    assert payload["movies"][0]["item_type"] == "movie"
    assert payload["series"][0]["item_type"] == "series"
    text = repr(payload).lower()
    assert "authorization" not in text
    assert "cookie" not in text
    assert "token=" not in text
    assert "stream_url" not in text


def test_search_keeps_result_types(monkeypatch):
    monkeypatch.setattr(content, "_live_rows", lambda limit, offset=0, q="", country="", category="": [
        ("ch", "Busca", "BR", "[]", None, 0),
    ])
    monkeypatch.setattr(content, "_movie_rows", lambda limit, offset=0, q="": [
        ("m", "Busca Filme", 2025, None, None, None, None, 1),
    ])
    monkeypatch.setattr(content, "_series_rows", lambda limit, offset=0, q="": [
        ("s", "Busca Série", 2024, None, None, None, None, 0),
    ])

    payload = content.search(q="busca", limit=10)
    assert payload["query"] == "busca"
    assert payload["movies"][0]["item_type"] == "movie"
    assert payload["series"][0]["item_type"] == "series"


def test_playback_resolve_returns_only_galodoidotv_url_and_safe_traits(monkeypatch):
    candidate = UpstreamCandidate(
        "stream-1",
        "https://provider.example/live/master.m3u8?token=SUPER_SECRET",
        {"Authorization": "Bearer PRIVATE", "Cookie": "sid=PRIVATE"},
        90,
    )
    monkeypatch.setattr(playback_api.gateway, "_live_candidates", lambda item_id: [candidate])
    monkeypatch.setattr(playback_api.gateway, "rank_candidates", lambda candidates, profile, kind: candidates)
    monkeypatch.setattr(
        playback_api.gateway,
        "_probe_media",
        lambda candidate: SimpleNamespace(
            status_code=200,
            content_type="application/vnd.apple.mpegurl",
            mime_type="application/x-mpegURL",
            protocol="hls",
            container="hls",
        ),
    )
    monkeypatch.setattr(playback_api.gateway, "_client_base", lambda request: "http://galodoidotv.local:8080")
    monkeypatch.setattr(
        playback_api.gateway,
        "candidate_diagnostic",
        lambda candidate, profile, kind: {
            "protocol": "hls",
            "container": "hls",
            "video_codec": "hevc",
            "audio_codec": "aac",
            "width": 1920,
            "height": 1080,
            "hdr": None,
            "audio_channels": 2.0,
        },
    )
    request = SimpleNamespace(headers={"x-familystream-device": "android-tv-modern"})

    payload = playback_api.resolve_playback("live", "channel-1", request)
    assert payload["playback_url"] == "http://galodoidotv.local:8080/api/v1/play/live/channel-1"
    assert payload["mime_type"] == "application/x-mpegURL"
    assert payload["video_codec"] == "hevc"
    text = repr(payload)
    assert "SUPER_SECRET" not in text
    assert "provider.example" not in text
    assert "Bearer PRIVATE" not in text
    assert "sid=PRIVATE" not in text


def test_episode_resolve_uses_opaque_episode_playback_route(monkeypatch):
    candidate = UpstreamCandidate("ep-stream", "https://provider.example/episode.mp4?secret=x", score=50)
    monkeypatch.setattr(playback_api.gateway, "_vod_candidates", lambda item_id: [candidate])
    monkeypatch.setattr(playback_api.gateway, "rank_candidates", lambda candidates, profile, kind: candidates)
    monkeypatch.setattr(
        playback_api.gateway,
        "_probe_media",
        lambda candidate: SimpleNamespace(
            status_code=206,
            content_type="video/mp4",
            mime_type="video/mp4",
            protocol="direct",
            container="mp4",
        ),
    )
    monkeypatch.setattr(playback_api.gateway, "_client_base", lambda request: "https://galodoidotv.example")
    monkeypatch.setattr(
        playback_api.gateway,
        "candidate_diagnostic",
        lambda candidate, profile, kind: {
            "protocol": "direct",
            "container": "mp4",
            "video_codec": "h264",
            "audio_codec": "aac",
            "width": 1280,
            "height": 720,
            "hdr": None,
            "audio_channels": 2.0,
        },
    )
    request = SimpleNamespace(headers={})
    payload = playback_api.resolve_playback("episode", "ep-1", request)
    assert payload["playback_url"] == "https://galodoidotv.example/api/v1/play/episode/ep-1"
    assert payload["mime_type"] == "video/mp4"
    assert "provider.example" not in repr(payload)
