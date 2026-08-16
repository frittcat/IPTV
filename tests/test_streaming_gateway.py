from backend.streaming_gateway import (
    UpstreamCandidate,
    choose_candidate,
    is_hls,
    request_headers_for_upstream,
    response_headers_for_client,
    rewrite_hls_manifest,
    upstream_status_usable,
)


def test_rejects_auth_and_not_found_statuses():
    assert not upstream_status_usable(401)
    assert not upstream_status_usable(403)
    assert not upstream_status_usable(404)
    assert upstream_status_usable(200)
    assert upstream_status_usable(206)


def test_candidate_selection_skips_bad_http_status():
    candidates = [
        UpstreamCandidate("bad", "https://x/bad", score=100),
        UpstreamCandidate("good", "https://x/good", score=80),
    ]
    statuses = {"bad": 403, "good": 206}
    selected = choose_candidate(candidates, lambda c: statuses[c.id])
    assert selected is not None
    assert selected.id == "good"


def test_hls_detection_by_type_extension_and_body():
    assert is_hls("application/vnd.apple.mpegurl")
    assert is_hls("text/plain", "https://x/master.m3u8?token=x")
    assert is_hls("text/plain", body_prefix="\n#EXTM3U\n")
    assert not is_hls("video/mp4", "https://x/movie.mp4")


def test_hls_rewrites_relative_variant_segments_keys_audio_and_subtitles():
    manifest = """#EXTM3U
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID=\"a\",URI=\"audio/pt.m3u8\"
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID=\"s\",URI=\"subs/pt.m3u8\"
#EXT-X-KEY:METHOD=AES-128,URI=\"keys/key.bin\"
#EXT-X-MAP:URI=\"init.mp4\"
variant/720.m3u8
segment001.ts
"""
    rewritten = rewrite_hls_manifest(
        manifest,
        "https://media.example/path/master.m3u8",
        lambda url: "https://galo/gateway?u=" + url,
    )
    assert "https://galo/gateway?u=https://media.example/path/audio/pt.m3u8" in rewritten
    assert "https://galo/gateway?u=https://media.example/path/subs/pt.m3u8" in rewritten
    assert "https://galo/gateway?u=https://media.example/path/keys/key.bin" in rewritten
    assert "https://galo/gateway?u=https://media.example/path/init.mp4" in rewritten
    assert "https://galo/gateway?u=https://media.example/path/variant/720.m3u8" in rewritten
    assert "https://galo/gateway?u=https://media.example/path/segment001.ts" in rewritten


def test_client_secrets_are_not_forwarded_but_range_is():
    headers = request_headers_for_upstream(
        {"Authorization": "Bearer provider-secret", "Cookie": "provider=session", "User-Agent": "ProviderUA"},
        {"Authorization": "Bearer client-secret", "Cookie": "client=session", "Range": "bytes=100-200"},
    )
    assert headers["Authorization"] == "Bearer provider-secret"
    assert headers["Cookie"] == "provider=session"
    assert headers["Range"] == "bytes=100-200"


def test_provider_user_agent_and_referer_win_over_player_headers():
    headers = request_headers_for_upstream(
        {"User-Agent": "ProviderUA", "Referer": "https://provider.example/"},
        {"User-Agent": "ExoPlayer", "Referer": "http://192.168.1.21/", "Range": "bytes=0-"},
    )
    assert headers["User-Agent"] == "ProviderUA"
    assert headers["Referer"] == "https://provider.example/"
    assert headers["Range"] == "bytes=0-"


def test_response_header_filter_keeps_range_metadata():
    filtered = response_headers_for_client(
        {
            "Content-Type": "video/mp4",
            "Content-Range": "bytes 0-99/1000",
            "Accept-Ranges": "bytes",
            "Set-Cookie": "secret=x",
            "Server": "upstream",
        }
    )
    assert filtered["Content-Type"] == "video/mp4"
    assert filtered["Content-Range"] == "bytes 0-99/1000"
    assert filtered["Accept-Ranges"] == "bytes"
    assert "Set-Cookie" not in filtered
    assert "Server" not in filtered
