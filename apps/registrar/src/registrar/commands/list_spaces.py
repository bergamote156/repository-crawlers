"""
`registrar list-spaces` — discovery helper that prints every space the
configured Oneprovider knows about, so the user can pick a concrete
`--space.id` for a deterministic `register` invocation.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import sys
from dataclasses import dataclass

import requests

from registrar import output
from registrar.api.onepanel import OnepanelClient
from registrar.api.utils import MissingTokenError
from registrar.config import ListSpacesConfig, effective_log_level


@dataclass(frozen=True)
class _SpaceRow:
    id: str
    name: str
    storage_id: str


def run(config: ListSpacesConfig) -> int:
    """List spaces on the configured Oneprovider."""
    output.set_level(effective_log_level(config.logging))

    try:
        onepanel = OnepanelClient.from_config(config)
        rows = _fetch(onepanel)
    except MissingTokenError as exc:
        return _fail(str(exc))
    except requests.RequestException as exc:
        return _fail(f"failed to fetch spaces: {exc}")

    _write_table(rows, sys.stdout)
    return 0


def _fetch(onepanel: OnepanelClient) -> tuple[_SpaceRow, ...]:
    rows: list[_SpaceRow] = []
    for space_id in onepanel.list_spaces():
        details = onepanel.get_space_details(space_id)
        rows.append(
            _SpaceRow(
                id=space_id,
                name=details.get("name") or "",
                storage_id=details.get("storageId") or "",
            ),
        )
    rows.sort(key=lambda r: (r.name.lower(), r.id))
    return tuple(rows)


def _write_table(rows: tuple[_SpaceRow, ...], out) -> None:
    out.write(f"\nSpaces ({len(rows)}):\n\n")
    out.write(f"{'Name':<40} {'Space ID':<40} {'Storage ID'}\n")
    out.write("-" * 100 + "\n")
    for row in rows:
        out.write(f"{row.name:<40} {row.id:<40} {row.storage_id}\n")


def _fail(message: str) -> int:
    sys.stderr.write(f"error: {message}\n")
    return 1
