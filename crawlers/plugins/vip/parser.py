"""
VIP Parser.

Parses raw Girder folder dicts (with pre-fetched files) into VipDataset models.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass, field
from typing import Sequence

from crawlers.plugins.vip.api import VipFile
from crawlers.processors.parsers import Parser
from crawlers.ui import console


@dataclass
class VipDataset:
    """
    VIP Girder folder mapped to a dataset model.

    Satisfies the Dataset, DataCiteDataset, and Serializable protocols
    via duck typing:
      - Dataset:         identifier, title, files
      - DataCiteDataset: identifier, title, datetime, geometry, files, self_link
      - Serializable:    to_json()
    """

    identifier: str
    title: str
    files: Sequence[VipFile]

    description: str | None = None
    datetime: str | None = None
    geometry: dict | None = None
    self_link: str | None = None

    # Selected fields from the Girder folder `meta` dict
    meta: dict = field(default_factory=dict)

    _raw: dict = field(default_factory=dict, repr=False, compare=False)

    def to_json(self) -> dict:
        """Serialize to a JSON-safe dict for JSONL output."""
        return {
            "identifier": self.identifier,
            "title": self.title,
            "description": self.description,
            "datetime": self.datetime,
            "self_link": self.self_link,
            "meta": self.meta,
            "files": [{"name": f.name, "url": f.url} for f in self.files],
        }


# pylint: disable=too-few-public-methods
class VipParser(Parser[dict, VipDataset]):
    """
    Parses a raw Girder folder dict (as yielded by VipClient.iterate_datasets)
    into a VipDataset.

    The raw dict must contain:
      - 'folder': Girder folder JSON object
      - 'files':  list[VipFile] collected by the client
    """

    def parse(self, raw: dict) -> VipDataset | None:
        """
        Parse raw folder data into a VipDataset.

        Args:
            raw: Dict with 'folder' and 'files' keys.

        Returns:
            VipDataset on success, None if the data is invalid.
        """
        folder = raw.get("folder", {})
        folder_id = folder.get("_id")
        if not folder_id:
            console.warning("VIP folder record missing '_id' field — skipping")
            return None

        files: list[VipFile] = raw.get("files", [])
        if not files:
            console.debug(f"Skipping folder {folder_id}: no files found")
            return None

        title = folder.get("name") or folder_id
        meta: dict = folder.get("meta", {})

        # Prefer TITLE from meta when available (e.g. "Parameter List, ...")
        description = meta.get("TITLE") or folder.get("description") or None

        # Use the most recent timestamp available
        datetime_val = folder.get("updated") or folder.get("created") or None

        return VipDataset(
            identifier=folder_id,
            title=title,
            files=files,
            description=description,
            datetime=datetime_val,
            meta=meta,
            _raw=raw,
        )
