"""
Path collision resolution helpers for plugin parsers.

Used by plugins whose source API exposes a flat list of file URLs without
hierarchical structure (e.g. eCUDO). The default path is the URL's last
segment (filename); on collision, additional parent segments are progressively
prepended until paths are unique within the dataset.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from collections import Counter
from urllib.parse import urlparse

_FALLBACK_NAME = "data.bin"


def resolve_path_collisions(urls: list[str]) -> list[str]:
    """
    Build unique relative paths from a list of file URLs.

    Args:
        urls: List of file URLs in the order they should be processed.

    Returns:
        List of unique relative paths, one per input URL, in the same order.
    """
    if not urls:
        return []

    segments_per_url = [_get_path_segments(u) for u in urls]
    used_count = [1] * len(urls)
    max_segments = max((len(s) for s in segments_per_url), default=1)
    unresolved = set(range(len(urls)))

    for _ in range(max_segments):
        counter: Counter[str] = Counter()
        paths: dict[int, str] = {}
        for idx in unresolved:
            paths[idx] = _build_path(segments_per_url[idx], used_count[idx])
            counter[paths[idx]] += 1

        colliding = {p for p, c in counter.items() if c > 1}
        next_unresolved: set[int] = set()
        for idx in unresolved:
            if paths[idx] in colliding and used_count[idx] < len(segments_per_url[idx]):
                used_count[idx] += 1
                next_unresolved.add(idx)

        if not next_unresolved:
            break
        unresolved = next_unresolved

    return [_build_path(segments_per_url[i], used_count[i]) for i in range(len(urls))]


def _get_path_segments(url: str) -> list[str]:
    """Extract URL path segments in reverse order (filename first)."""
    try:
        path = urlparse(url).path
        segments = [seg for seg in path.split("/") if seg][::-1]
    except (ValueError, AttributeError):
        return [_FALLBACK_NAME]
    return segments or [_FALLBACK_NAME]


def _build_path(segments: list[str], count: int) -> str:
    """Build a path from the first 'count' reversed segments."""
    used = segments[:count]
    return "/".join(reversed(used))
