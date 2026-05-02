"""
Cross-cutting types and constants shared across all confline layers.

Lives at the bottom of the dependency stack — every other confline
module is allowed to import from here. Holds the alphabet that
schema, sources, resolution, errors, and UI all speak.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import MISSING, dataclass
from typing import Final, TypeAlias

FieldPath: TypeAlias = tuple[str, ...]
"""Dotted schema path as a tuple — `("db", "host")` for `db.host`."""

SECRET_PLACEHOLDER: Final[str] = "******"
"""Single placeholder for redacted secret values across the framework."""

MISSING_DEFAULT = MISSING
"""Public alias for `dataclasses.MISSING`.

Aliased rather than redefined so the sentinel users compare against
is exactly the one the loader runs internally — `field.default is
MISSING_DEFAULT` is an identity check, not equality.
"""


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where a resolved field's value came from.

    Powers two features:

    - `ConfigBase.source_of(path)` — public API for "where did this
      value come from?", used by ops dashboards and audit logs.
    - cross-source mutex enforcement — `mutex.py` distinguishes
      user-provided values (anything but `DefaultSource`) from
      defaults, catching cases argparse's own check misses (e.g. a
      YAML file setting two mutex-grouped fields at once).

    `name` is the source's stable identity (`yaml`, `argparse`,
    `env`, `default`, or a custom source's `name`); used for dispatch
    and registry lookup.

    `label` is the human-readable form (`"yaml /etc/app.yaml"`,
    `"command line"`, `"environment"`, …); used by error rendering.
    Falls back to `name` when no source attached extra detail.
    """

    name: str
    label: str
