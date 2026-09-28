from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

try:
    from .episode_gap import calculate_missing_episodes
except ImportError:  # direct execution by regression tests
    from episode_gap import calculate_missing_episodes


def build_season_record(
    tmdb_id: int,
    title: str,
    season: int,
    total_episodes: int,
    collected_episodes: Iterable[object] | None,
    aired_episode_numbers: Iterable[object] | None,
    subscription_id: int | None = None,
    previous: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build OneSRM-compatible per-season state from observable library data."""
    now = _utc(now)
    collected = _numbers(collected_episodes or [])
    aired = _numbers(aired_episode_numbers or [])
    missing = calculate_missing_episodes(
        total_episodes=total_episodes,
        collected_episodes=collected,
        known_episode_numbers=aired,
    )
    if not missing:
        state = "ok"
    elif old_state := (previous or {}).get("season_state"):
        state = old_state if old_state in {"queued", "failed"} else ("backfill_needed" if not collected else "missing")
    elif not collected:
        state = "backfill_needed"
    else:
        state = "missing"

    old = previous or {}
    return {
        "series_tmdb_id": int(tmdb_id),
        "title": str(title),
        "season_number": int(season),
        "total_episodes": int(total_episodes or 0),
        "collected_episodes": collected,
        "missing_episodes": missing,
        "season_state": state,
        "subscription_id": subscription_id,
        "attempt_count": int(old.get("attempt_count") or 0) if missing else 0,
        "last_attempt_at": old.get("last_attempt_at") if missing else None,
        "last_error": old.get("last_error") if missing else "",
        "last_scanned_at": now.isoformat(),
    }


def mark_attempt(
    record: dict[str, Any],
    success: bool,
    now: datetime | None = None,
    error: str = "",
) -> dict[str, Any]:
    result = dict(record)
    result["attempt_count"] = int(result.get("attempt_count") or 0) + 1
    result["last_attempt_at"] = _utc(now).isoformat()
    result["last_error"] = "" if success else str(error or "search/download failed")
    result["season_state"] = "queued" if success else "failed"
    return result


def should_attempt(
    record: dict[str, Any],
    now: datetime | None = None,
    retry_hours: float = 24,
) -> bool:
    if not record.get("missing_episodes"):
        return False
    last_attempt = record.get("last_attempt_at")
    if not last_attempt:
        return True
    try:
        then = datetime.fromisoformat(str(last_attempt).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    return _utc(now) >= _utc(then) + timedelta(hours=max(0.0, float(retry_hours)))


def _numbers(values: Iterable[object]) -> list[int]:
    result: set[int] = set()
    for value in values:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            result.add(number)
    return sorted(result)


def _utc(value: datetime | None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
