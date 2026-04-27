"""Metadata record protocol."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from typing import Protocol


# pylint: disable=too-few-public-methods
class MetadataRecord(Protocol):
    """Protocol for metadata records."""

    def to_xml(self) -> str:
        """Generate XML metadata for the dataset."""
