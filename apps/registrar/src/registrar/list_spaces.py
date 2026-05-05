"""Discovery helper that prints every space the configured Oneprovider knows about."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import sys

import requests

from registrar import output
from registrar.api.onepanel import OnepanelClient, SpaceDetails
from registrar.api.utils import MissingTokenError
from registrar.config import ListSpacesConfig, effective_log_level


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


def _fetch(onepanel: OnepanelClient) -> tuple[tuple[str, SpaceDetails], ...]:
    rows = [(sid, onepanel.get_space_details(sid)) for sid in onepanel.list_spaces()]
    rows.sort(key=lambda r: (r[1]["name"].lower(), r[0]))
    return tuple(rows)


def _write_table(rows: tuple[tuple[str, SpaceDetails], ...], out) -> None:
    out.write(f"\nSpaces ({len(rows)}):\n\n")
    out.write(f"{'Name':<40} {'Space ID':<40} {'Storage ID'}\n")
    out.write("-" * 100 + "\n")

    for space_id, details in rows:
        out.write(f"{details['name']:<40} {space_id:<40} {details['storageId']}\n")


def _fail(message: str) -> int:
    sys.stderr.write(f"error: {message}\n")
    return 1
