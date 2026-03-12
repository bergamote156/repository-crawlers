"""
EODC Data Models.

Models for STAC items from EODC Earth Observation Data Centre.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass, field
from typing import Sequence


@dataclass
class EODCFile:
    """Asset from STAC item."""

    name: str
    url: str


# pylint: disable=too-many-instance-attributes
@dataclass
class EODCDataset:
    """
    EODC STAC Item mapped to dataset model.

    Satisfies Dataset protocol from converters.py (identifier, title, files)
    and DataCiteDataset protocol from datacite.py.
    """

    # Core identifiers (required by Dataset protocol)
    identifier: str  # STAC item id
    title: str  # generated title
    files: Sequence[EODCFile]

    # Spatial/temporal (for DataCite metadata)
    geometry: dict | None = None  # GeoJSON polygon
    datetime: str | None = None

    # Links
    self_link: str | None = None  # URL to STAC item

    # Raw STAC item data
    _raw: dict = field(default_factory=dict, repr=False, compare=False)

    def to_json(self) -> dict:
        """Return the raw STAC item data."""
        return self._raw
