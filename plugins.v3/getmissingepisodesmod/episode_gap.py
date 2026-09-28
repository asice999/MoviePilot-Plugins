from __future__ import annotations

from collections.abc import Iterable


def calculate_missing_episodes(
    total_episodes: int,
    collected_episodes: Iterable[object] | None,
    known_episode_numbers: Iterable[object] | None = None,
) -> list[int]:
    """Return aired/known episode numbers absent from the media library.

    Subscription state is deliberately not an input: an existing season
    subscription does not prove that every episode has been collected.
    """
    try:
        total = int(total_episodes)
    except (TypeError, ValueError):
        return []
    if total <= 0:
        return []

    expected = set(range(1, total + 1))
    if known_episode_numbers is not None:
        expected &= _valid_episode_numbers(known_episode_numbers)

    return sorted(expected - _valid_episode_numbers(collected_episodes or []))


def _valid_episode_numbers(values: Iterable[object]) -> set[int]:
    result: set[int] = set()
    for value in values:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            result.add(number)
    return result
