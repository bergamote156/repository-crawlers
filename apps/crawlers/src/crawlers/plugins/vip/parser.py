"""
VIP parser.

Maps a Girder folder (plus its recursively collected files) into a
`DataCiteRecord` and the list of downloadable files. This module has
no knowledge of the crawler lifecycle or HTTP — it is pure mapping, so
it can be unit-tested in isolation and the plugin file stays focused
on lifecycle wiring.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from collections.abc import Sequence
from dataclasses import dataclass

from crawlers.core import JsonObject
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
from crawlers.plugins.utils.datetime import year_from_iso
from crawlers.plugins.vip.api import VipFile
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
class ParsedVipRecord:
    """Result of parsing a single VIP Girder folder."""

    identifier: str
    title: str
    metadata: DataCiteRecord
    files: list[VipFile]


def parse_vip_record(folder: JsonObject, files: Sequence[VipFile]) -> ParsedVipRecord | None:
    """
    Map a Girder folder dict (with pre-collected files) into a `ParsedVipRecord`.

    Returns `None` when the record should be silently skipped (missing
    `_id` or empty file list).
    """
    folder_id = folder.get("_id")
    if not folder_id:
        console.warning("VIP folder record missing '_id' field — skipping")
        return None

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
        publication_year=year_from_iso(datetime_val),
        resource_type_general="Dataset",
        resource_type_value=_VIP_RESOURCE_TYPE_VALUE,
        subjects=_subjects_from_meta(meta),
        dates=([Date(value=datetime_val, date_type=DateType.UPDATED)] if datetime_val else []),
        descriptions=([Description(value=description)] if description else []),
        rights_list=[_VIP_RIGHTS],
    )

    return ParsedVipRecord(
        identifier=folder_id,
        title=title,
        metadata=record,
        files=list(files),
    )


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
