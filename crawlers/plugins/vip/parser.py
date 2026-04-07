"""
VIP Parser.

Parses raw Girder folder dicts (with pre-fetched files) into VipDataset models.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Sequence

from crawlers.metadata.datacite import (
    Creator,
    DataCiteRecord,
    Date,
    DateType,
    Description,
    IdentifierType,
    NameType,
    Rights,
)
from crawlers.plugins.vip.api import VipFile
from crawlers.processors.parsers import Parser
from crawlers.ui import console

# VIP defaults — moved here from the legacy VipDataCiteBuilder.
_VIP_DEFAULT_CREATOR_NAME = "VIP"
_VIP_PUBLISHER = "VIP (Virtual Imaging Platform)"
_VIP_RESOURCE_TYPE_VALUE = "Medical imaging data"
_VIP_RIGHTS = Rights(text="Contact data owner for usage terms")

# Meta keys whose values are emitted as DataCite subjects, in this order.
_SUBJECT_META_KEYS = (
    "SUBJECT_study_modalities",
    "SUBJECT_type",
    "SUBJECT_gender",
    "SUBJECT_id",
    "SUBJECT_name_string",
    "SUBJECT_study_instrument_position",
    "SUBJECT_study_operator",
    "ORIGIN",
    "DATATYPE",
)


@dataclass
class VipDataset:
    """Pipeline carrier for a VIP Girder folder with prebuilt DataCite record."""

    identifier: str
    title: str
    files: Sequence[VipFile]
    metadata_record: DataCiteRecord
    _raw: dict = field(default_factory=dict, repr=False, compare=False)

    def to_json(self) -> dict:
        """Serialize to a JSON-safe dict for JSONL output."""
        return {
            "identifier": self.identifier,
            "title": self.title,
            "files": [{"path": f.path, "url": f.url} for f in self.files],
        }


# pylint: disable=too-few-public-methods
class VipParser(Parser[dict, VipDataset]):
    """
    Parses a resolved Girder folder dict into a VipDataset.

    Expects the dict produced by VipClient.resolve_dataset():
      - 'folder': Girder folder JSON object
      - 'files':  list[VipFile] collected recursively
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

        record = DataCiteRecord(
            identifier=folder_id,
            identifier_type=IdentifierType.OTHER,
            creators=[
                Creator(
                    name=meta.get("OWNER") or _VIP_DEFAULT_CREATOR_NAME,
                    name_type=NameType.PERSONAL,
                )
            ],
            title=title,
            publisher=_VIP_PUBLISHER,
            publication_year=_year_from_datetime(datetime_val),
            resource_type_general="Dataset",
            resource_type_value=_VIP_RESOURCE_TYPE_VALUE,
            subjects=_subjects_from_meta(meta),
            dates=(
                [Date(value=datetime_val, date_type=DateType.UPDATED)]
                if datetime_val
                else []
            ),
            descriptions=([Description(value=description)] if description else []),
            rights_list=[_VIP_RIGHTS],
        )

        return VipDataset(
            identifier=folder_id,
            title=title,
            files=files,
            metadata_record=record,
            _raw=raw,
        )


def _year_from_datetime(dt: str | None) -> int:
    """Extract year from ISO 8601 string, fall back to UTC now."""
    if dt:
        try:
            return int(dt[:4])
        except (ValueError, IndexError):
            pass
    return datetime.now(UTC).year


def _subjects_from_meta(meta: dict) -> list[str]:
    """Pick the subject-relevant values from the Girder folder meta dict."""
    seen: set[str] = set()
    subjects: list[str] = []
    for key in _SUBJECT_META_KEYS:
        value = meta.get(key)
        if value and value not in seen:
            seen.add(value)
            subjects.append(value)
    return subjects
