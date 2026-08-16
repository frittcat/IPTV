from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class MediaProbeResult:
    protocol: str | None = None
    container: str | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    width: int | None = None
    height: int | None = None
    bitrate: int | None = None
    fps: float | None = None
    hdr: str | None = None
    audio_channels: float | None = None
    probe_status: str = "ok"

    def public_dict(self) -> dict[str, Any]:
        # Intentionally contains no URL, request headers, stderr or provider data.
        return asdict(self)


def _int(value: Any) -> int | None:
    try:
        if value in (None, "", "N/A"):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        if value in (None, "", "N/A"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _fps(value: Any) -> float | None:
    if not value or value in {"0/0", "N/A"}:
        return None
    text = str(value)
    if "/" not in text:
        return _float(text)
    left, right = text.split("/", 1)
    try:
        denominator = float(right)
        if denominator == 0:
            return None
        return round(float(left) / denominator, 3)
    except (TypeError, ValueError):
        return None


def normalize_video_codec(codec: str | None) -> str | None:
    value = (codec or "").strip().lower()
    aliases = {
        "h265": "hevc",
        "hev1": "hevc",
        "hvc1": "hevc",
        "avc": "h264",
        "avc1": "h264",
        "x264": "h264",
        "x265": "hevc",
    }
    return aliases.get(value, value or None)


def normalize_audio_codec(codec: str | None) -> str | None:
    value = (codec or "").strip().lower().replace("-", "")
    aliases = {
        "eac3": "eac3",
        "ac3": "ac3",
        "mp4a": "aac",
    }
    return aliases.get(value, value or None)


def _container(format_name: str | None) -> str | None:
    names = {part.strip().lower() for part in (format_name or "").split(",") if part.strip()}
    if "hls" in names or "applehttp" in names:
        return "hls"
    if names & {"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}:
        return "mp4"
    if "mpegts" in names:
        return "mpegts"
    if "matroska" in names:
        return "matroska"
    if "webm" in names:
        return "webm"
    return sorted(names)[0] if names else None


def _hdr(video: dict[str, Any]) -> str | None:
    transfer = str(video.get("color_transfer") or "").lower()
    primaries = str(video.get("color_primaries") or "").lower()
    if transfer in {"smpte2084", "smpte2084-pq"}:
        return "hdr10/pq"
    if transfer in {"arib-std-b67", "hlg"}:
        return "hlg"
    if "bt2020" in primaries:
        return "bt2020"
    return None


def parse_ffprobe_payload(payload: dict[str, Any]) -> MediaProbeResult:
    streams = payload.get("streams") or []
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    audios = [stream for stream in streams if stream.get("codec_type") == "audio"]

    # Prefer the largest video stream when manifests expose more than one stream.
    video = max(
        videos,
        key=lambda stream: (_int(stream.get("width")) or 0) * (_int(stream.get("height")) or 0),
        default={},
    )
    audio = audios[0] if audios else {}
    fmt = payload.get("format") or {}

    container = _container(fmt.get("format_name"))
    protocol = "hls" if container == "hls" else ("direct" if container else None)
    fps = _fps(video.get("avg_frame_rate")) or _fps(video.get("r_frame_rate"))
    bitrate = _int(fmt.get("bit_rate")) or _int(video.get("bit_rate"))

    status = "ok" if (video or audio or container) else "empty"
    return MediaProbeResult(
        protocol=protocol,
        container=container,
        video_codec=normalize_video_codec(video.get("codec_name")),
        audio_codec=normalize_audio_codec(audio.get("codec_name")),
        width=_int(video.get("width")),
        height=_int(video.get("height")),
        bitrate=bitrate,
        fps=fps,
        hdr=_hdr(video),
        audio_channels=_float(audio.get("channels")),
        probe_status=status,
    )


def build_ffprobe_command(target_url: str) -> list[str]:
    """Build a bounded ffprobe command for an opaque FamilyStream gateway URL.

    Provider Authorization/Cookie headers are deliberately not accepted here.
    Authenticated media must be exposed to ffprobe through the short-lived opaque
    gateway route so secrets never appear in the child process command line.
    """
    return [
        "ffprobe",
        "-v", "error",
        "-hide_banner",
        "-analyzeduration", "5000000",
        "-probesize", "5000000",
        "-show_streams",
        "-show_format",
        "-of", "json",
        target_url,
    ]


def run_ffprobe(target_url: str, timeout_seconds: int = 20) -> MediaProbeResult:
    command = build_ffprobe_command(target_url)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(3, min(int(timeout_seconds), 60)),
            check=False,
        )
    except FileNotFoundError:
        return MediaProbeResult(probe_status="ffprobe_unavailable")
    except subprocess.TimeoutExpired:
        return MediaProbeResult(probe_status="timeout")

    if completed.returncode != 0:
        # Do not persist or return raw stderr; ffprobe can echo source URLs.
        return MediaProbeResult(probe_status=f"ffprobe_exit_{completed.returncode}")
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return MediaProbeResult(probe_status="invalid_json")
    return parse_ffprobe_payload(payload)


def persist_probe(
    db_execute: Callable[..., Any],
    stream_id: str,
    item_kind: str,
    result: MediaProbeResult,
) -> None:
    if item_kind not in {"live", "vod"}:
        raise ValueError("item_kind must be live or vod")
    timestamp = datetime.now(timezone.utc).isoformat()
    db_execute(
        "INSERT INTO stream_technical_profiles("
        "stream_id,item_kind,protocol,container,video_codec,audio_codec,width,height,bitrate,fps,hdr,audio_channels,probe_status,probed_at"
        ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(stream_id,item_kind) DO UPDATE SET "
        "protocol=excluded.protocol,container=excluded.container,video_codec=excluded.video_codec,"
        "audio_codec=excluded.audio_codec,width=excluded.width,height=excluded.height,bitrate=excluded.bitrate,"
        "fps=excluded.fps,hdr=excluded.hdr,audio_channels=excluded.audio_channels,"
        "probe_status=excluded.probe_status,probed_at=excluded.probed_at",
        (
            stream_id,
            item_kind,
            result.protocol,
            result.container,
            result.video_codec,
            result.audio_codec,
            result.width,
            result.height,
            result.bitrate,
            result.fps,
            result.hdr,
            result.audio_channels,
            result.probe_status,
            timestamp,
        ),
    )
