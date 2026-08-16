from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Callable, Any

MASTER_PATH = Path(__file__).resolve().parents[1] / "data" / "live_master_br.json"


def _norm(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    # A plus sign is semantically meaningful in channel brands such as HBO+
    # and SportyNet+. Preserve it as a word before punctuation is stripped so
    # those aliases cannot collide with HBO/SportyNet.
    text = text.replace("+", " plus ")
    return "".join(ch for ch in text if ch.isalnum())


@lru_cache(maxsize=1)
def master_payload() -> dict:
    return json.loads(MASTER_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def master_channels() -> tuple[dict, ...]:
    return tuple(master_payload().get("channels") or [])


@lru_cache(maxsize=1)
def _alias_index() -> dict[str, dict]:
    result: dict[str, dict] = {}
    for channel in master_channels():
        for label in [channel.get("name"), *(channel.get("aliases") or [])]:
            key = _norm(str(label or ""))
            if key:
                result.setdefault(key, channel)
    return result


def categories() -> list[str]:
    return list(master_payload().get("categories") or [])


def match_channel(name: str | None) -> dict | None:
    return _alias_index().get(_norm(name))


def decorate_channel(item: dict) -> dict:
    """Attach stable BR navigation metadata without exposing any stream source."""
    if str(item.get("country") or "").upper() != "BR":
        return item
    target = match_channel(str(item.get("name") or ""))
    if target is None:
        item["section"] = "Outros"
        item["master_target"] = False
        return item
    item["section"] = target["category"]
    item["master_target"] = True
    item["master_name"] = target["name"]
    item["priority"] = target.get("priority", "P2")
    item["premium"] = bool(target.get("premium", False))
    return item


def _state(status: dict | None) -> str:
    if status is None:
        return "missing_catalog"
    if status["source_count"] == 0:
        return "catalog_no_source"
    if status["healthy_sources"] == 0:
        return "source_unhealthy"
    if not status["published"]:
        return "healthy_unpublished"
    return "playable"


def coverage_report(db_execute: Callable[..., Any]) -> dict:
    rows = db_execute(
        "SELECT c.id,c.name,c.published,"
        "(SELECT COUNT(*) FROM streams s WHERE s.channel_id=c.id) AS source_count,"
        "(SELECT COUNT(*) FROM streams s WHERE s.channel_id=c.id AND s.status IN ('healthy','degraded')) AS healthy_sources,"
        "(SELECT COUNT(*) FROM streams s WHERE s.channel_id=c.id AND s.status='offline') AS offline_sources "
        "FROM channels c WHERE c.country='BR' ORDER BY c.name",
        fetch=True,
    )

    matched: dict[str, dict] = {}
    unmapped_available: list[dict] = []
    for channel_id, name, published, source_count, healthy_sources, offline_sources in rows:
        target = match_channel(name)
        candidate = {
            "id": channel_id,
            "name": name,
            "published": bool(published),
            "source_count": int(source_count or 0),
            "healthy_sources": int(healthy_sources or 0),
            "offline_sources": int(offline_sources or 0),
        }
        if target is None:
            if candidate["healthy_sources"]:
                unmapped_available.append(candidate)
            continue
        key = target["name"]
        current = matched.get(key)
        # Prefer the match with the most usable sources, then the largest source
        # inventory. This makes aliases deterministic when upstream has variants.
        rank = (candidate["healthy_sources"], candidate["source_count"], candidate["published"])
        current_rank = (
            current["healthy_sources"], current["source_count"], current["published"]
        ) if current else (-1, -1, False)
        if current is None or rank > current_rank:
            matched[key] = candidate

    items = []
    by_category: dict[str, dict[str, int]] = {
        category: {"target": 0, "known": 0, "with_source": 0, "healthy": 0, "playable": 0}
        for category in categories()
    }
    for target in master_channels():
        status = matched.get(target["name"])
        category = target["category"]
        by_category.setdefault(
            category,
            {"target": 0, "known": 0, "with_source": 0, "healthy": 0, "playable": 0},
        )
        by_category[category]["target"] += 1
        if status is not None:
            by_category[category]["known"] += 1
        if status is not None and status["source_count"] > 0:
            by_category[category]["with_source"] += 1
        if status is not None and status["healthy_sources"] > 0:
            by_category[category]["healthy"] += 1
        playable = bool(status and status["healthy_sources"] > 0 and status["published"])
        if playable:
            by_category[category]["playable"] += 1
        items.append({
            "name": target["name"],
            "category": category,
            "priority": target.get("priority", "P2"),
            "premium": bool(target.get("premium", False)),
            "known": status is not None,
            "source_count": status["source_count"] if status else 0,
            "healthy_sources": status["healthy_sources"] if status else 0,
            "offline_sources": status["offline_sources"] if status else 0,
            "playable": playable,
            "state": _state(status),
            "matched_name": status["name"] if status else None,
            "channel_id": status["id"] if status else None,
        })

    target_total = len(items)
    known = sum(1 for item in items if item["known"])
    with_source = sum(1 for item in items if item["source_count"] > 0)
    healthy = sum(1 for item in items if item["healthy_sources"] > 0)
    playable = sum(1 for item in items if item["playable"])
    states: dict[str, int] = {}
    for item in items:
        states[item["state"]] = states.get(item["state"], 0) + 1
    return {
        "country": "BR",
        "target": target_total,
        "known": known,
        "with_source": with_source,
        "healthy": healthy,
        "playable": playable,
        "missing_or_unplayable": target_total - playable,
        "coverage_percent": round((playable / target_total) * 100.0, 1) if target_total else 0.0,
        "states": states,
        "by_category": by_category,
        "items": items,
        "unmapped_available": unmapped_available,
    }
