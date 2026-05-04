"""
Ecudo JSON-LD parser.

Maps a dcat JSON-LD record (as returned by the eCUDO REST API) to an
`OnedataDataset` carrying an OpenAIRE metadata payload. This module has
no knowledge of the crawler lifecycle or HTTP — it is pure mapping and
schema validation, so it can be unit-tested in isolation and so the
plugin file stays focused on lifecycle wiring.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from typing import Any

from crawlers.core import JsonObject, Ok
from crawlers.core.dataset import OnedataDataset, OnedataFile
from crawlers.metadata.openaire import (
    AccessRights,
    BoundingBox,
    FileLocation,
    OpenAIRERecord,
    ResourceType,
)
from crawlers.plugins.utils.language import normalize_language_code
from crawlers.plugins.utils.mime import infer_mime_type
from crawlers.plugins.utils.paths import resolve_path_collisions
from crawlers.ui import console

# --- Schema expectations -----------------------------------------------------

_EXPECTED_TYPES = {
    "root": "dcat:Dataset",
    "distribution": "dcat:Distribution",
    "publisher": "org:Organization",
    "contactPoint": "vCard:contact",
}
_BOUNDING_BOX_COORDS = 4

_KNOWN_ROOT_FIELDS = {
    "@context",
    "@type",
    "accessLevel",
    "contactPoint",
    "description",
    "distribution",
    "identifier",
    "issued",
    "keywords",
    "language",
    "license",
    "modified",
    "publisher",
    "spatial",
    "temporal",
    "title",
}

_KNOWN_ACCESS_LEVELS = {"public"}

_ACCESS_LEVEL_MAP: dict[str, AccessRights] = {
    "public": AccessRights.OPEN,
}


# --- Entry point -------------------------------------------------------------


def parse_ecudo_record(raw: JsonObject) -> Ok[OnedataDataset] | None:
    """
    Map a raw eCUDO JSON-LD dict into an `OnedataDataset`.

    Returns `None` when the record should be silently skipped (missing
    identifier, no distributions, no valid download URLs). Schema
    deviations are logged as warnings but do not stop parsing.
    """
    identifier = raw.get("identifier")
    if not identifier:
        return None

    _validate_structure(raw, identifier)

    distributions = raw.get("distribution", [])
    if not distributions:
        console.debug(f"Skipping {identifier}: no distribution URLs")
        return None

    files = _parse_files(distributions, identifier)
    if not files:
        console.debug(f"Skipping {identifier}: no valid download URLs")
        return None

    title = raw.get("title", "Untitled Dataset")
    publisher = _parse_publisher(raw.get("publisher"), identifier)

    metadata = OpenAIRERecord(
        title=title,
        creator=publisher,
        identifier=identifier,
        publication_date=str(raw.get("issued", raw.get("modified", "")) or ""),
        access_rights=_resolve_access_rights(raw.get("accessLevel", "public")),
        resource_type=ResourceType.DATASET,
        language=normalize_language_code(raw.get("language", "en")),
        publisher=publisher,
        description=raw.get("description") or None,
        subjects=list(raw.get("keywords", [])),
        files=[FileLocation(url=f.url, mime_type=infer_mime_type(f.url)) for f in files],
        temporal_coverage=raw.get("temporal"),
        spatial_coverage=_parse_bounding_box(raw.get("spatial")),
    )

    return Ok(
        OnedataDataset(
            name=title,
            target_dir=title.replace("/", "-"),
            pid=identifier,
            metadata_xml=metadata.to_xml(),
            files=tuple(files),
        )
    )


# --- Internals ---------------------------------------------------------------


def _validate_structure(raw: dict, identifier: str) -> None:
    """Warn on unexpected schema deviations; never raises."""
    root_type = raw.get("@type")
    if root_type and root_type != _EXPECTED_TYPES["root"]:
        console.warning(
            f"Unexpected root @type '{root_type}' (expected '{_EXPECTED_TYPES['root']}')"
            f" in record {identifier}"
        )

    unknown_fields = set(raw.keys()) - _KNOWN_ROOT_FIELDS
    if unknown_fields:
        console.warning(
            f"Unknown fields {sorted(unknown_fields)} in record {identifier} - consider"
            " updating parser"
        )

    access_level = raw.get("accessLevel")
    if access_level and access_level not in _KNOWN_ACCESS_LEVELS:
        console.warning(
            f"Unknown accessLevel '{access_level}' in record {identifier} - verify COAR mapping"
        )

    publisher = raw.get("publisher")
    if isinstance(publisher, dict):
        pub_type = publisher.get("@type")
        if pub_type and pub_type != _EXPECTED_TYPES["publisher"]:
            console.warning(
                f"Unexpected publisher @type '{pub_type}' (expected"
                f" '{_EXPECTED_TYPES['publisher']}') in record {identifier}"
            )

    contact = raw.get("contactPoint")
    if isinstance(contact, dict):
        contact_type = contact.get("@type")
        if contact_type and contact_type != _EXPECTED_TYPES["contactPoint"]:
            console.warning(
                f"Unexpected contactPoint @type '{contact_type}' (expected"
                f" '{_EXPECTED_TYPES['contactPoint']}') in record {identifier}"
            )


def _parse_files(distributions: list, identifier: str) -> list[OnedataFile]:
    """Parse a JSON-LD distribution array into a list of `OnedataFile`."""
    urls: list[str] = []
    for dist in distributions:
        dist_type = dist.get("@type")
        if dist_type and dist_type != _EXPECTED_TYPES["distribution"]:
            console.warning(
                f"Unexpected distribution @type '{dist_type}' (expected"
                f" '{_EXPECTED_TYPES['distribution']}') in record {identifier}"
            )

        url = dist.get("downloadURL")
        if not url:
            continue
        urls.append(url)

    paths = resolve_path_collisions(urls)
    return [OnedataFile(path=p, url=u) for p, u in zip(paths, urls, strict=True)]


def _parse_publisher(publisher_data: Any, identifier: str) -> str:
    """Parse the publisher field which can be a dict, a string, or missing."""
    if not publisher_data:
        return "Unknown Publisher"

    if isinstance(publisher_data, dict):
        return publisher_data.get("name", "Unknown Publisher")

    if isinstance(publisher_data, str):
        return publisher_data

    console.warning(
        f"Unexpected publisher type {type(publisher_data).__name__} in record {identifier}"
    )
    return "Unknown Publisher"


def _resolve_access_rights(level: str | None) -> AccessRights:
    if level and level in _ACCESS_LEVEL_MAP:
        return _ACCESS_LEVEL_MAP[level]

    if level:
        console.warning(f"Unknown eCUDO accessLevel '{level}', defaulting to open access.")

    return AccessRights.OPEN


def _parse_bounding_box(spatial: str | None) -> BoundingBox | None:
    """Parse an eCUDO 'spatial' string ("west,south,east,north")."""
    if not spatial:
        return None
    try:
        coords = [float(x.strip()) for x in spatial.split(",")]
    except ValueError:
        console.warning(f"Could not parse spatial coordinates '{spatial}'")
        return None

    if len(coords) != _BOUNDING_BOX_COORDS:
        console.warning(f"Expected 4 spatial coordinates, got {len(coords)}: '{spatial}'")
        return None

    west, south, east, north = coords
    return BoundingBox(west=west, south=south, east=east, north=north)
