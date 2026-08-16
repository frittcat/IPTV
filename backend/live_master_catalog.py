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


def coverage_report(db_execute: Callable[..., Any]) -> dict:
    rows = db_execute(
        "SELECT c.id,c.name,c.published,"
        "CASE WHEN EXISTS(SELECT 1 FROM streams s WHERE s.channel_id=c.id AND s.status IN ('healthy','degraded')) THEN 1 ELSE 0 END "
        "FROM channels c WHERE c.country='BR' ORDER BY c.name",
        fetch=True,
    )

    matched: dict[str, dict] = {}
    unmapped_available: list[dict] = []
    for channel_id, name, published, healthy in rows:
        target = match_channel(name)
        if target is None:
            if healthy:
                unmapped_available.append({"id": channel_id, "name": name, "published": bool(published)})
            continue
        key = target["name"]
        current = matched.get(key)
        candidate = {
            "id": channel_id,
            "name": name,
            "published": bool(published),
            "healthy": bool(healthy),
        }
        if current is None or (candidate["healthy"], candidate["published"]) > (current["healthy"], current["published"]):
            matched[key] = candidate

    items = []
    by_category: dict[str, dict[str, int]] = {
        category: {"target": 0, "known": 0, "playable": 0}
        for category in categories()
    }
    for target in master_channels():
        status = matched.get(target["name"])
        category = target["category"]
        by_category.setdefault(category, {"target": 0, "known": 0, "playable": 0})
        by_category[category]["target"] += 1
        if status is not None:
            by_category[category]["known"] += 1
        if status is not None and status["healthy"] and status["published"]:
            by_category[category]["playable"] += 1
        items.append({
            "name": target["name"],
            "category": category,
            "priority": target.get("priority", "P2"),
            "premium": bool(target.get("premium", False)),
            "known": status is not None,
            "playable": bool(status and status["healthy"] and status["published"]),
            "matched_name": status["name"] if status else None,
            "channel_id": status["id"] if status else None,
        })

    playable = sum(1 for item in items if item["playable"])
    known = sum(1 for item in items if item["known"])
    target_total = len(items)
    return {
        "country": "BR",
        "target": target_total,
        "known": known,
        "playable": playable,
        "missing_or_unplayable": target_total - playable,
        "coverage_percent": round((playable / target_total) * 100.0, 1) if target_total else 0.0,
        "by_category": by_category,
        "items": items,
        "unmapped_available": unmapped_available,
    }
