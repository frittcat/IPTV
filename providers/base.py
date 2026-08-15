from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol


@dataclass
class VODItem:
    provider_id: str
    provider_item_id: str
    item_type: str
    title: str
    year: int | None = None
    plot: str | None = None
    genres: list[str] = field(default_factory=list)
    poster: str | None = None
    backdrop: str | None = None
    stream_url: str | None = None
    quality: str | None = None
    license: str | None = None
    license_url: str | None = None
    creator: str | None = None
    attribution: str | None = None
    rights_status: str = "review_required"
    metadata: dict[str, Any] = field(default_factory=dict)
    series_id: str | None = None
    season_number: int | None = None
    episode_number: int | None = None


class VODProvider(Protocol):
    provider_id: str

    def discover(self, **kwargs: Any) -> Iterable[VODItem]: ...
    def sync(self, **kwargs: Any) -> Iterable[VODItem]: ...
    def categories(self) -> list[str]: ...
    def resolve_stream(self, item: VODItem) -> str | None: ...
    def health_check(self, item: VODItem) -> dict[str, Any]: ...


def rights_status(license_name: str | None, rights: str | None, license_url: str | None) -> str:
    text = " ".join(x or "" for x in (license_name, rights, license_url)).lower()
    approved = ("public domain" in text or "cc0" in text or "creative commons attribution" in text or "cc by" in text or "cc-by" in text)
    return "approved" if approved else "review_required"
