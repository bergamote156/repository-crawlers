"""Discovery helper that prints every space the configured Oneprovider knows about."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import sys

import requests
from rich import box
from rich.table import Table

from registrar.api.onepanel import OnepanelClient, SpaceDetails
from registrar.api.utils import MissingTokenError
from registrar.config import ListSpacesConfig, effective_log_level
from registrar.logging_config import setup_logging
from registrar.ui.console import get_console


def run(config: ListSpacesConfig) -> int:
    """List spaces on the configured Oneprovider."""
    console = get_console()
    setup_logging(console=console, level=effective_log_level(config.logging))

    try:
        onepanel = OnepanelClient.from_config(config)
        rows = _fetch(onepanel)
    except MissingTokenError as exc:
        return _fail(str(exc))
    except requests.RequestException as exc:
        return _fail(f"failed to fetch spaces: {exc}")

    if not rows:
        console.print(f"[muted]No spaces found on {config.onedata.oneprovider_domain}.[/]")
        return 0

    table = Table(
        title=f"Spaces on {config.onedata.oneprovider_domain}  ({len(rows)} found)",
        title_style="bold",
        box=box.SIMPLE_HEAVY,
        show_edge=False,
    )
    table.add_column("Name", no_wrap=False, overflow="fold")
    table.add_column("Space ID")
    table.add_column("Storage ID")

    for space_id, details in rows:
        table.add_row(details["name"], space_id, details["storageId"])

    console.print()
    console.print(table)
    return 0


def _fetch(onepanel: OnepanelClient) -> tuple[tuple[str, SpaceDetails], ...]:
    rows = [(sid, onepanel.get_space_details(sid)) for sid in onepanel.list_spaces()]
    rows.sort(key=lambda r: (r[1]["name"].lower(), r[0]))
    return tuple(rows)


def _fail(message: str) -> int:
    sys.stderr.write(f"error: {message}\n")
    return 1
