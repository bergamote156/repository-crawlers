"""
`registrar list-storages` — discovery helper that prints every storage
on the configured Oneprovider, flagging which ones are compatible with
the registrar (HTTP readonly imported), so the user can pick a concrete
`--storage.id` for a deterministic `register` invocation.
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
from registrar.config import ListStoragesConfig, effective_log_level


@dataclass(frozen=True)
class _StorageRow:
    id: str
    name: str
    type: str
    readonly: bool
    imported: bool
    endpoint: str

    @property
    def is_compatible(self) -> bool:
        return self.type == "http" and self.readonly and self.imported


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


def _fetch(onepanel: OnepanelClient) -> tuple[_StorageRow, ...]:
    rows: list[_StorageRow] = []
    for storage_id in onepanel.list_storages():
        details = onepanel.get_storage_details(storage_id)
        rows.append(
            _StorageRow(
                id=storage_id,
                name=details.get("name") or "",
                type=details.get("type") or "",
                readonly=bool(details.get("readonly", False)),
                imported=bool(details.get("importedStorage", False)),
                endpoint=details.get("endpoint") or "",
            ),
        )
    rows.sort(key=lambda r: (r.name.lower(), r.id))
    return tuple(rows)


def _write_table(rows: tuple[_StorageRow, ...], out) -> None:
    out.write(f"\nStorages ({len(rows)}):\n\n")
    out.write(f"{'Name':<40} {'Storage ID':<40} {'Type':<10} {'Compat':<7} {'Endpoint'}\n")
    out.write("-" * 110 + "\n")
    for row in rows:
        compat = "yes" if row.is_compatible else "no"
        out.write(
            f"{row.name:<40} {row.id:<40} {row.type:<10} {compat:<7} {row.endpoint}\n",
        )


def _fail(message: str) -> int:
    sys.stderr.write(f"error: {message}\n")
    return 1
