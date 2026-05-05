"""Discovery helper that prints every storage on the configured Oneprovider."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import sys

import requests

from registrar import output
from registrar.api.onepanel import OnepanelClient, StorageDetails, is_storage_compatible
from registrar.api.utils import MissingTokenError
from registrar.config import ListStoragesConfig, effective_log_level


def run(config: ListStoragesConfig) -> int:
    """List storages on the configured Oneprovider."""
    output.set_level(effective_log_level(config.logging))

    try:
        onepanel = OnepanelClient.from_config(config)
        rows = _fetch(onepanel)
    except MissingTokenError as exc:
        return _fail(str(exc))
    except requests.RequestException as exc:
        return _fail(f"failed to fetch storages: {exc}")

    _write_table(rows, sys.stdout)
    return 0


def _fetch(onepanel: OnepanelClient) -> tuple[tuple[str, StorageDetails], ...]:
    rows = [(sid, onepanel.get_storage_details(sid)) for sid in onepanel.list_storages()]
    rows.sort(key=lambda r: (r[1]["name"].lower(), r[0]))
    return tuple(rows)


def _write_table(rows: tuple[tuple[str, StorageDetails], ...], out) -> None:
    out.write(f"\nStorages ({len(rows)}):\n\n")
    out.write(f"{'Name':<40} {'Storage ID':<40} {'Type':<10} {'Compat':<7} {'Endpoint'}\n")
    out.write("-" * 110 + "\n")

    for storage_id, details in rows:
        compat = "yes" if is_storage_compatible(details) else "no"
        out.write(
            f"{details['name']:<40} {storage_id:<40} {details['type']:<10} "
            f"{compat:<7} {details.get('endpoint', '')}\n",
        )


def _fail(message: str) -> int:
    sys.stderr.write(f"error: {message}\n")
    return 1
