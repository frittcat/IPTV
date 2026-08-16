from backend.app_v03 import app
from backend.media_probe import (
    build_ffprobe_command,
    parse_ffprobe_payload,
)


def test_parse_ffprobe_hevc_hdr_audio_and_bitrate():
    result = parse_ffprobe_payload({
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "hevc",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "25/1",
                "color_transfer": "smpte2084",
                "color_primaries": "bt2020",
            },
            {
                "codec_type": "audio",
                "codec_name": "eac3",
                "channels": 6,
            },
        ],
        "format": {
            "format_name": "hls",
            "bit_rate": "4850000",
        },
    })
    assert result.probe_status == "ok"
    assert result.protocol == "hls"
    assert result.container == "hls"
    assert result.video_codec == "hevc"
    assert result.audio_codec == "eac3"
    assert result.width == 1920
    assert result.height == 1080
    assert result.bitrate == 4_850_000
    assert result.fps == 25.0
    assert result.hdr == "hdr10/pq"
    assert result.audio_channels == 6.0


def test_parse_ffprobe_normalizes_h264_and_mp4():
    result = parse_ffprobe_payload({
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": "1280", "height": "720", "r_frame_rate": "30000/1001"},
            {"codec_type": "audio", "codec_name": "aac", "channels": "2"},
        ],
        "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
    })
    assert result.container == "mp4"
    assert result.protocol == "direct"
    assert result.video_codec == "h264"
    assert result.audio_codec == "aac"
    assert result.fps == 29.97


def test_empty_ffprobe_payload_is_not_marked_ok():
    assert parse_ffprobe_payload({}).probe_status == "empty"


def test_ffprobe_command_contains_only_target_not_provider_headers():
    target = "http://127.0.0.1:8080/api/v1/gateway/hls/opaque-session/opaque-resource"
    command = build_ffprobe_command(target)
    text = " ".join(command)
    assert target in command
    assert "Authorization" not in text
    assert "Cookie" not in text
    assert "provider-secret" not in text


def test_media_probe_routes_are_activated():
    paths = [getattr(route, "path", None) for route in app.router.routes]
    assert paths.count("/api/v1/playback/probe/{kind}/{stream_id}") == 1
    assert paths.count("/api/v1/playback/technical/{kind}/{stream_id}") == 1
