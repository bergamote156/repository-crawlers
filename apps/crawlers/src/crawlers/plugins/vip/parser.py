"""
VIP parser.

Maps a Girder folder (plus its recursively collected files) into an
`OnedataDataset` carrying a DataCite metadata payload. This module has
no knowledge of the crawler lifecycle or HTTP — it is pure mapping, so
it can be unit-tested in isolation and the plugin file stays focused
on lifecycle wiring.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import re
from collections.abc import Sequence

from crawlers.core import JsonObject
from crawlers.core.dataset import OnedataDataset, OnedataFile
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


def parse_vip_record(
    folder: JsonObject,
    files: Sequence[VipFile],
    folders_meta: dict[str, JsonObject],
) -> OnedataDataset | None:
    """
    Map a Girder folder dict (with pre-collected files) into an `OnedataDataset`.

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

    description = _description_from_meta(meta, folders_meta)

    # Use the most recent timestamp available
    datetime_val = folder.get("updated") or folder.get("created") or None

    subject = meta.get("SUBJECT_study_modalities") or None

    metadata = DataCiteRecord(
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
        subjects=[subject] if subject else [],
        dates=([Date(value=datetime_val, date_type=DateType.UPDATED)] if datetime_val else []),
        descriptions=([Description(value=description)] if description else []),
        rights_list=[_VIP_RIGHTS],
    )

    return OnedataDataset(
        name=title,
        target_dir=title.replace("/", "-"),
        # This repository doesn't provide Persistent Identifiers for its datasets
        pid=None,
        metadata_xml=metadata.to_xml(),
        files=tuple(OnedataFile(path=f.path, url=f.url) for f in files),
    )


def _description_from_meta(meta: JsonObject, folders_meta: dict[str, JsonObject]) -> str:
    gender = meta.get("SUBJECT_gender") or "unknown"
    weight = meta.get("SUBJECT_study_weight") or "unknown"
    date_of_birth = meta.get("SUBJECT_study_dbirth") or "unknown"
    manufacturer = meta.get("ORIGIN") or "unknown"

    description = (
        f"\ngender:{gender}\n"
        f"weight:{weight}\n"
        f"dateofbirth:{date_of_birth}\n"
        f"manufacturer:{manufacturer}\n"
    )
    days = [key for key in folders_meta if key.startswith("/day")]

    species = "unknown"
    organ = "unknown"

    for day in days:
        day_meta = folders_meta[day].get("meta", {})
        if day_meta.get("species") is not None:
            species = f"{day_meta.get('species')}"
        if day_meta.get("organe") is not None:
            organ = f"{day_meta.get('organe')}"

    description += f"species:{species}\norgan:{organ}\n"

    working_carrier_frequency = "unknown"
    nucleus = "unknown"

    method = [key for key in folders_meta if re.search(r"STEAM[^/]*/headers/method$", key)]

    for key in method:
        day_meta = folders_meta[key].get("meta", {})
        if day_meta.get("PVM_FrqRef") is not None and working_carrier_frequency == "unknown":
            working_carrier_frequency = f"{day_meta.get('PVM_FrqRef').split(' ')[0]}MHz"
        if day_meta.get("PVM_NucleiPpmWork") is not None and nucleus == "unknown":
            nucleus = f"{day_meta.get('PVM_NucleiPpmWork').split()[0].split('<')[1].split('>')[0]}"

    steam_press_last = [
        key for key in folders_meta if re.search(r"(STEAM[^/]*|PRESS[^/]*)/headers/method$", key)
    ]
    acquisition_sequence = "unknown"
    for key in steam_press_last:
        day_meta = folders_meta[key].get("meta", {})
        if day_meta.get("Method") is not None:
            acquisition_sequence = f"{day_meta.get('Method')}"

    description += (
        f"acquisition_sequence:{acquisition_sequence}\n"
        f"working_carrier_frequency:{working_carrier_frequency}\n"
        f"nucleus:{nucleus}\n"
    )

    return description
