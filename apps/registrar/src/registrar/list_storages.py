"""Discovery helper that prints every storage on the configured Oneprovider."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import sys

import requests
from rich import box
from rich.table import Table

from registrar.api.onepanel import OnepanelClient, StorageDetails, is_storage_compatible
from registrar.api.utils import MissingTokenError
from registrar.config import ListStoragesConfig, effective_log_level
from registrar.logging_config import setup_logging
from registrar.ui.console import get_console


def run(config: ListStoragesConfig) -> int:
    """List storages on the configured Oneprovider."""
    console = get_console()
    setup_logging(console=console, level=effective_log_level(config.logging))

    try:
        onepanel = OnepanelClient.from_config(config)
        rows = _fetch(onepanel)
    except MissingTokenError as exc:
        return _fail(str(exc))
    except requests.RequestException as exc:
        return _fail(f"failed to fetch storages: {exc}")

    if not rows:
        console.print(f"[muted]No storages found on {config.onedata.oneprovider_domain}.[/]")
        return 0

    table = Table(
        title=f"Storages on {config.onedata.oneprovider_domain}  ({len(rows)} found)",
        title_style="bold",
        box=box.SIMPLE_HEAVY,
        show_edge=False,
    )
    table.add_column("Name", no_wrap=False, overflow="fold")
    table.add_column("Storage ID")
    table.add_column("Type")
    table.add_column("Compat")
    table.add_column("Endpoint")

    for storage_id, details in rows:
        compat = _compat_cell(details)
        table.add_row(
            details["name"],
            storage_id,
            details["type"],
            compat,
            details.get("endpoint", "—"),
        )

    console.print()
    console.print(table)
    return 0


def _compat_cell(details: StorageDetails) -> str:
    if details["type"] not in ("http",):
        return "[muted]n/a[/]"

    if is_storage_compatible(details):
        return "[success]ok[/]"

    return "[danger]no[/]"


def _fetch(onepanel: OnepanelClient) -> tuple[tuple[str, StorageDetails], ...]:
    rows = [(sid, onepanel.get_storage_details(sid)) for sid in onepanel.list_storages()]
    rows.sort(key=lambda r: (r[1]["name"].lower(), r[0]))
    return tuple(rows)


def _fail(message: str) -> int:
    sys.stderr.write(f"error: {message}\n")
    return 1
