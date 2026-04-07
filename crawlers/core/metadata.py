"""Metadata Generator Base."""

# pylint: disable=too-few-public-methods

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from typing import Protocol


class MetadataRecord(Protocol):
    """Protocol for metadata records."""

    def to_xml(self) -> str:
        """Generate xml metadata for dataset."""
