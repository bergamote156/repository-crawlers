"""
On-demand Onepanel queries for the registration target.

Each function does the minimum API work for its question:
- `lookup_*_by_id` is one GET; `find_*_by_name` lists and scans only when
  ambiguity has to be ruled out. The planner orchestrates these calls
  based on what the user supplied via config.

No business errors are raised here. Misses surface as `None`, `()`, or
`""`; only `requests.RequestException` from unexpected HTTP failures
bubbles up.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from http import HTTPStatus
from urllib.parse import urlparse

import requests

from registrar.api.onepanel import (
    OnepanelClient,
    SpaceDetails,
    StorageDetails,
)

# ─────────────────────────────────────────────────────────────────────────────
# Single-resource lookups (1 GET each)
# ─────────────────────────────────────────────────────────────────────────────


def lookup_space_by_id(onepanel: OnepanelClient, space_id: str) -> SpaceDetails | None:
    """Return Onepanel's space details, or `None` when the ID is unknown."""
    try:
        return onepanel.get_space_details(space_id)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == HTTPStatus.NOT_FOUND:
            return None
        raise


def lookup_storage_by_id(onepanel: OnepanelClient, storage_id: str) -> StorageDetails | None:
    """Return Onepanel's storage details, or `None` when the ID is unknown."""
    try:
        return onepanel.get_storage_details(storage_id)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == HTTPStatus.NOT_FOUND:
            return None
        raise


# ─────────────────────────────────────────────────────────────────────────────
# Name searches (list + N×GET; exhaustive — ambiguity is the planner's call)
# ─────────────────────────────────────────────────────────────────────────────


def find_spaces_by_name(
    onepanel: OnepanelClient,
    name: str,
) -> tuple[tuple[str, SpaceDetails], ...]:
    """Return `(space_id, details)` pairs whose `name` matches exactly."""
    matches: list[tuple[str, SpaceDetails]] = []
    for space_id in onepanel.list_spaces():
        details = onepanel.get_space_details(space_id)
        if details["name"] == name:
            matches.append((space_id, details))

    return tuple(matches)


def find_storages_by_name(
    onepanel: OnepanelClient,
    name: str,
) -> tuple[tuple[str, StorageDetails], ...]:
    """Return `(storage_id, details)` pairs whose `name` matches exactly."""
    matches: list[tuple[str, StorageDetails]] = []
    for storage_id in onepanel.list_storages():
        details = onepanel.get_storage_details(storage_id)
        if details["name"] == name:
            matches.append((storage_id, details))

    return tuple(matches)


# ─────────────────────────────────────────────────────────────────────────────
# Pure helpers
# ─────────────────────────────────────────────────────────────────────────────


def is_storage_compatible(storage: StorageDetails) -> bool:
    """True for HTTP readonly imported storages (the only kind registrar can use)."""
    return storage["type"] == "http" and storage["readonly"] and storage["importedStorage"]


def infer_domain(url: str) -> str:
    """Domain part of `url`, or `""` when the URL has no netloc."""
    return urlparse(url).netloc or ""


def choose_endpoint(
    explicit_endpoint: str,
    first_file_url: str,
) -> tuple[str, bool] | None:
    """Pick the storage endpoint. Returns `(endpoint, inferred)` or `None`.

    `None` means neither source could produce a usable endpoint — the
    planner turns that into the operator-facing error.
    """
    if explicit_endpoint:
        return explicit_endpoint, False

    parsed = urlparse(first_file_url)
    if not parsed.scheme or not parsed.netloc:
        return None

    return f"{parsed.scheme}://{parsed.netloc}", True
