from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Mapping
from urllib.parse import urlparse

from backend.streaming_gateway import UpstreamCandidate


@dataclass(frozen=True, slots=True)
class DeviceProfile:
    id: str
    video_codecs: tuple[str, ...]
    audio_codecs: tuple[str, ...]
    max_height: int
    preferred_protocols: tuple[str, ...]
    prefer_hevc: bool = False


PROFILES: dict[str, DeviceProfile] = {
    "generic": DeviceProfile(
        id="generic",
        video_codecs=("h264", "avc", "hevc", "h265"),
        audio_codecs=("aac", "ac3", "eac3", "mp3"),
        max_height=2160,
        preferred_protocols=("hls", "direct", "http"),
    ),
    "android-tv-modern": DeviceProfile(
        id="android-tv-modern",
        video_codecs=("hevc", "h265", "h264", "avc"),
        audio_codecs=("aac", "ac3", "eac3", "mp3"),
        max_height=2160,
        preferred_protocols=("hls", "direct", "http"),
        prefer_hevc=True,
    ),
    "android-tv-legacy": DeviceProfile(
        id="android-tv-legacy",
        video_codecs=("h264", "avc"),
        audio_codecs=("aac", "ac3", "mp3"),
        max_height=1080,
        preferred_protocols=("hls", "direct", "http"),
    ),
    "web-tv": DeviceProfile(
        id="web-tv",
        video_codecs=("h264", "avc"),
        audio_codecs=("aac", "mp3"),
        max_height=1080,
        preferred_protocols=("hls", "direct", "http"),
    ),
    "roku": DeviceProfile(
        id="roku",
        video_codecs=("h264", "avc", "hevc", "h265"),
        audio_codecs=("aac", "ac3", "eac3"),
        max_height=2160,
        preferred_protocols=("hls", "direct", "http"),
    ),
}


@dataclass(frozen=True, slots=True)
class StreamTraits:
    protocol: str
    video_codec: str | None = None
    audio_codec: str | None = None
    height: int | None = None
    container: str | None = None


_CODEC_PATTERNS = (
    (re.compile(r"(?:^|[._\-/])(?:hevc|h265|x265)(?:[._\-/]|$)", re.I), "hevc"),
    (re.compile(r"(?:^|[._\-/])(?:h264|avc|x264)(?:[._\-/]|$)", re.I), "h264"),
)
_RESOLUTION_RE = re.compile(r"(?:^|[^0-9])(2160|1440|1080|720|576|480)p?(?:[^0-9]|$)", re.I)


def infer_traits(url: str) -> StreamTraits:
    parsed = urlparse(url)
    path = parsed.path.lower()
    if path.endswith(".m3u8"):
        protocol, container = "hls", "hls"
    elif path.endswith(".mp4"):
        protocol, container = "direct", "mp4"
    elif path.endswith(".mkv"):
        protocol, container = "direct", "mkv"
    elif path.endswith(".ts"):
        protocol, container = "direct", "mpegts"
    else:
        protocol, container = "http", None

    codec = None
    searchable = f"{parsed.path}?{parsed.query}"
    for pattern, value in _CODEC_PATTERNS:
        if pattern.search(searchable):
            codec = value
            break

    resolution = _RESOLUTION_RE.search(searchable)
    height = int(resolution.group(1)) if resolution else None
    return StreamTraits(protocol=protocol, video_codec=codec, height=height, container=container)


def get_profile(profile_id: str | None) -> DeviceProfile:
    key = (profile_id or "generic").strip().lower()
    return PROFILES.get(key, PROFILES["generic"])


def profile_from_headers(headers: Mapping[str, str]) -> DeviceProfile:
    base = get_profile(headers.get("x-familystream-device"))

    codecs_raw = headers.get("x-familystream-video-codecs")
    max_height_raw = headers.get("x-familystream-max-height")

    codecs = base.video_codecs
    if codecs_raw:
        parsed = tuple(
            token.strip().lower()
            for token in codecs_raw.split(",")
            if token.strip()
        )
        if parsed:
            codecs = parsed

    max_height = base.max_height
    if max_height_raw:
        try:
            requested = int(max_height_raw)
            if 240 <= requested <= 4320:
                max_height = requested
        except ValueError:
            pass

    return replace(base, video_codecs=codecs, max_height=max_height)


def compatibility_score(candidate: UpstreamCandidate, profile: DeviceProfile, kind: str) -> float:
    traits = infer_traits(candidate.url)
    value = float(candidate.score)

    if traits.video_codec and traits.video_codec not in profile.video_codecs:
        return -10000.0
    if traits.height and traits.height > profile.max_height:
        value -= 250.0

    try:
        protocol_index = profile.preferred_protocols.index(traits.protocol)
        value += max(0, 24 - protocol_index * 8)
    except ValueError:
        value -= 30.0

    if kind == "live" and traits.protocol == "hls":
        value += 18.0
    if kind == "vod" and traits.protocol == "direct":
        value += 10.0

    if profile.prefer_hevc and traits.video_codec == "hevc":
        value += 16.0
    elif traits.video_codec in {"h264", "avc"}:
        value += 6.0

    if traits.height:
        # Prefer the best resolution that still fits the client profile.
        value += min(traits.height, profile.max_height) / 240.0

    return value


def rank_candidates(
    candidates: list[UpstreamCandidate],
    profile: DeviceProfile,
    kind: str,
) -> list[UpstreamCandidate]:
    return sorted(
        candidates,
        key=lambda candidate: compatibility_score(candidate, profile, kind),
        reverse=True,
    )


def candidate_diagnostic(candidate: UpstreamCandidate, profile: DeviceProfile, kind: str) -> dict[str, object]:
    traits = infer_traits(candidate.url)
    return {
        "id": candidate.id,
        "profile": profile.id,
        "kind": kind,
        "protocol": traits.protocol,
        "video_codec_hint": traits.video_codec,
        "height_hint": traits.height,
        "container_hint": traits.container,
        "base_score": candidate.score,
        "resolver_score": compatibility_score(candidate, profile, kind),
        # Deliberately no upstream URL or headers here: diagnostics must never
        # become a secret/token exfiltration path.
    }
