"""Datetime parsing helpers shared across plugin parsers."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from datetime import UTC, datetime


def year_from_iso(dt: str | None) -> int:
    """Extract year from an ISO 8601 string, falling back to the current UTC year."""
    if dt:
        try:
            return int(dt[:4])
        except (ValueError, IndexError):
            pass

    return datetime.now(UTC).year
