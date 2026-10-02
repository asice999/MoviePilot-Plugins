from __future__ import annotations

from collections.abc import Iterable, Mapping


def normalize_title(title: object) -> str:
    """Whitespace-normalized, case-folded title used for identity comparisons."""
    return " ".join(str(title or "").split()).casefold()


def same_show_year(left: object, right: object) -> bool:
    """Whether two year values allow treating them as the same show.

    Lenient on purpose for subscription de-duplication: one side missing the
    year never causes a miss (a false miss would recreate duplicate
    subscriptions), while two different non-empty years are different shows.
    """
    a = str(left or "").strip()
    b = str(right or "").strip()
    if not a or not b:
        return True
    return a == b


def show_key(title: object, year: object) -> str:
    """Normalize a show identity for grouping duplicate media-server entries.

    TMDB and media servers may hold the same show under different TMDB IDs
    (duplicate entries) or split it across servers/libraries. Grouping by a
    whitespace-normalized, case-folded title plus year keeps different-year
    remakes with the same title separate while letting true duplicates merge.
    """
    text = normalize_title(title)
    return f"{text}|{str(year or '').strip()}"


def merge_seasoninfo_views(
    views: Iterable[Mapping[object, Iterable[object]] | None],
) -> dict[object, list[int]]:
    """Union collected episodes per season across duplicate entries of one show.

    Each view follows the plugin's ``seasoninfo`` shape (season -> episodes).
    Episodes that exist in any sibling entry count as collected, so a partial
    duplicate entry no longer reports phantom missing episodes that another
    entry already has on disk. Int-parseable season keys are unified first so
    str/int variants from different servers join the same union; the result
    exposes both ``1`` and ``"1"`` spellings so downstream lookups written
    against either type keep working.
    """
    canonical: dict[int, set[int]] = {}
    opaque: dict[object, set[int]] = {}
    for view in views:
        if not view:
            continue
        for season, episodes in view.items():
            try:
                bucket = canonical.setdefault(int(season), set())
            except (TypeError, ValueError):
                bucket = opaque.setdefault(season, set())
            bucket.update(_valid_episode_numbers(episodes or []))
    result: dict[object, list[int]] = {key: sorted(value) for key, value in {**canonical, **opaque}.items()}
    for key in canonical:
        result.setdefault(str(key), result[key])
    return result


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
