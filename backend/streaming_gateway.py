from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Mapping
from urllib.parse import urljoin

HLS_CONTENT_TYPES = {
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "audio/mpegurl",
    "audio/x-mpegurl",
}

PASSTHROUGH_RESPONSE_HEADERS = {
    "accept-ranges",
    "cache-control",
    "content-length",
    "content-range",
    "content-type",
    "etag",
    "last-modified",
}

# Headers that are useful for media interoperability and safe to forward from
# an authenticated provider adapter into the server-side gateway. Secrets stay
# server-side and are never exposed to clients.
PASSTHROUGH_REQUEST_HEADERS = {
    "accept",
    "accept-language",
    "if-match",
    "if-none-match",
    "if-modified-since",
    "if-unmodified-since",
    "range",
    "referer",
    "user-agent",
}


@dataclass(slots=True)
class UpstreamCandidate:
    id: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    score: float = 0.0


def upstream_status_usable(status_code: int) -> bool:
    """Return True only for statuses that can represent a usable media source.

    v0.2 treated every status below 500 as reachable, which allowed 401/403/404
    candidates to win selection. Redirects normally disappear because httpx is
    configured with follow_redirects=True, but 3xx is intentionally accepted for
    adapters/probes that surface them before following.
    """
    return 200 <= status_code < 400


def is_partial_content(status_code: int) -> bool:
    return status_code == 206


def is_hls(content_type: str | None, url: str = "", body_prefix: str = "") -> bool:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    return (
        media_type in HLS_CONTENT_TYPES
        or url.lower().split("?", 1)[0].endswith(".m3u8")
        or body_prefix.lstrip().startswith("#EXTM3U")
    )


def response_headers_for_client(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() in PASSTHROUGH_RESPONSE_HEADERS
    }


def request_headers_for_upstream(
    provider_headers: Mapping[str, str] | None,
    client_headers: Mapping[str, str] | None,
) -> dict[str, str]:
    """Merge server-side provider headers with safe playback request headers.

    Provider headers win except Range/HTTP validators supplied by the playback
    client. Authorization/Cookie may exist in provider_headers and remain only on
    the server-side request; client Authorization/Cookie are deliberately ignored.
    """
    result = dict(provider_headers or {})
    for key, value in (client_headers or {}).items():
        if key.lower() in PASSTHROUGH_REQUEST_HEADERS:
            # Preserve conventional header spelling where possible while allowing
            # clients to override seek/validator headers for the current request.
            existing = next((k for k in result if k.lower() == key.lower()), None)
            if existing:
                result[existing] = value
            else:
                result[key] = value
    return result


def choose_candidate(
    candidates: list[UpstreamCandidate],
    probe: Callable[[UpstreamCandidate], int | None],
) -> UpstreamCandidate | None:
    """Pick the highest-ranked candidate that returns a usable HTTP status."""
    for candidate in sorted(candidates, key=lambda item: item.score, reverse=True):
        status = probe(candidate)
        if status is not None and upstream_status_usable(status):
            return candidate
    return None


_URI_ATTRIBUTE = re.compile(r'URI=(?P<quote>["\'])(?P<uri>.*?)(?P=quote)')


def rewrite_hls_manifest(
    manifest: str,
    upstream_url: str,
    proxy_url: Callable[[str], str],
) -> str:
    """Rewrite every HLS URI so playback remains inside FamilyStream Gateway.

    Handles normal media/variant lines plus URI="..." attributes used by keys,
    maps, alternate audio/subtitles and initialization segments.
    """

    def absolute(uri: str) -> str:
        return urljoin(upstream_url, uri.strip())

    def rewrite_attributes(line: str) -> str:
        def replace(match: re.Match[str]) -> str:
            quote = match.group("quote")
            return f"URI={quote}{proxy_url(absolute(match.group('uri')))}{quote}"

        return _URI_ATTRIBUTE.sub(replace, line)

    output: list[str] = []
    for raw_line in manifest.splitlines():
        line = raw_line.strip()
        if not line:
            output.append(raw_line)
            continue
        if line.startswith("#"):
            output.append(rewrite_attributes(raw_line))
            continue
        output.append(proxy_url(absolute(line)))

    trailing_newline = "\n" if manifest.endswith(("\n", "\r")) else ""
    return "\n".join(output) + trailing_newline
