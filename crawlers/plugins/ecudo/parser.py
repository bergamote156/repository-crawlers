"""
Ecudo Parser.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass, field
from typing import Sequence

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
from crawlers.processors.parsers import Parser
from crawlers.ui import console

# Expected @type values for structure validation
EXPECTED_TYPES = {
    "root": "dcat:Dataset",
    "distribution": "dcat:Distribution",
    "publisher": "org:Organization",
    "contactPoint": "vCard:contact",
}

# Known root-level fields in ECUDO JSON-LD records
KNOWN_ROOT_FIELDS = {
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

# Known accessLevel values
KNOWN_ACCESS_LEVELS = {"public"}

# Maps eCUDO ``accessLevel`` strings to COAR access right enums.
_ACCESS_LEVEL_MAP: dict[str, AccessRights] = {
    "public": AccessRights.OPEN,
}


@dataclass
class EcudoFile:
    """File from Ecudo dataset."""

    path: str
    url: str


@dataclass
class EcudoDataset:
    """
    Pipeline carrier for an eCUDO dataset.

    Holds the minimal fields the processor pipeline needs (identifier, title,
    files) plus a fully populated :class:`OpenAIRERecord` for the metadata
    builder, and the original JSON-LD payload for the raw sink.
    """

    identifier: str
    title: str
    files: Sequence[EcudoFile]
    metadata: OpenAIRERecord
    _raw: dict = field(default_factory=dict, repr=False, compare=False)

    def to_json(self) -> dict:
        """Return the raw JSON-LD data."""
        return self._raw


# pylint: disable=too-few-public-methods
class EcudoParser(Parser[dict, EcudoDataset]):
    """
    Parses Ecudo JSON-LD into EcudoDataset.
    """

    def parse(self, raw: dict) -> EcudoDataset | None:
        """
        Parse raw JSON-LD data.

        Args:
            raw: Dictionary with JSON-LD data

        Returns:
            EcudoDataset or None if parsing fails or data is invalid
        """
        identifier = raw.get("identifier")
        if not identifier:
            return None

        try:
            return _parse_record(raw, identifier)
        except Exception as e:  # pylint: disable=broad-except
            console.warning(f"Failed to parse record {identifier}: {e}")
            return None


def _parse_record(raw: dict, identifier: str) -> EcudoDataset | None:
    """Internal parsing logic."""
    validate_structure(raw, identifier)

    distributions = raw.get("distribution", [])
    if not distributions:
        console.debug(f"Skipping {identifier}: no distribution URLs")
        return None

    files = parse_files(distributions, identifier)
    if not files:
        console.debug(f"Skipping {identifier}: no valid download URLs")
        return None

    title = raw.get("title", "Untitled Dataset")
    publisher = parse_publisher(raw.get("publisher"), identifier)
    description = raw.get("description", "") or None
    keywords = list(raw.get("keywords", []))
    issued = raw.get("issued", raw.get("modified", ""))
    language = raw.get("language", "en")
    access_level = raw.get("accessLevel", "public")
    spatial = raw.get("spatial")
    temporal = raw.get("temporal")

    metadata = OpenAIRERecord(
        title=title,
        creator=publisher,
        identifier=identifier,
        publication_date=issued,
        access_rights=_resolve_access_rights(access_level),
        resource_type=ResourceType.DATASET,
        language=normalize_language_code(language),
        publisher=publisher,
        description=description,
        subjects=keywords,
        files=[
            FileLocation(url=f.url, mime_type=infer_mime_type(f.url)) for f in files
        ],
        temporal_coverage=temporal,
        spatial_coverage=_parse_bounding_box(spatial),
    )

    return EcudoDataset(
        identifier=identifier,
        title=title,
        files=files,
        metadata=metadata,
        _raw=raw,
    )


def _resolve_access_rights(level: str | None) -> AccessRights:
    if level and level in _ACCESS_LEVEL_MAP:
        return _ACCESS_LEVEL_MAP[level]

    if level:
        console.warning(
            f"Unknown eCUDO accessLevel '{level}', defaulting to open access."
        )

    return AccessRights.OPEN


def _parse_bounding_box(spatial: str | None) -> BoundingBox | None:
    """Parse an eCUDO ``spatial`` string ("west,south,east,north")."""
    if not spatial:
        return None
    try:
        coords = [float(x.strip()) for x in spatial.split(",")]
    except ValueError:
        console.warning(f"Could not parse spatial coordinates '{spatial}'")
        return None

    if len(coords) != 4:
        console.warning(
            f"Expected 4 spatial coordinates, got {len(coords)}: '{spatial}'"
        )
        return None

    west, south, east, north = coords
    return BoundingBox(west=west, south=south, east=east, north=north)


def validate_structure(raw: dict, identifier: str) -> None:
    """
    Validate record structure and log warnings for unexpected values.

    This helps detect schema changes or new record types during crawling.

    Args:
        raw: Raw JSON-LD dict
        identifier: Record identifier for logging context
    """
    # Check root @type
    root_type = raw.get("@type")
    if root_type and root_type != EXPECTED_TYPES["root"]:
        console.warning(
            f"Unexpected root @type '{root_type}' (expected '{EXPECTED_TYPES['root']}')"
            f" in record {identifier}"
        )

    # Check for unknown root fields
    unknown_fields = set(raw.keys()) - KNOWN_ROOT_FIELDS
    if unknown_fields:
        console.warning(
            f"Unknown fields {sorted(unknown_fields)} in record {identifier} - consider"
            " updating parser"
        )

    # Check accessLevel
    access_level = raw.get("accessLevel")
    if access_level and access_level not in KNOWN_ACCESS_LEVELS:
        console.warning(
            f"Unknown accessLevel '{access_level}' in record {identifier} - verify COAR"
            " mapping"
        )

    # Check publisher @type if present
    publisher = raw.get("publisher")
    if isinstance(publisher, dict):
        pub_type = publisher.get("@type")
        if pub_type and pub_type != EXPECTED_TYPES["publisher"]:
            console.warning(
                f"Unexpected publisher @type '{pub_type}' (expected"
                f" '{EXPECTED_TYPES['publisher']}') in record {identifier}"
            )

    # Check contactPoint @type if present
    contact = raw.get("contactPoint")
    if isinstance(contact, dict):
        contact_type = contact.get("@type")
        if contact_type and contact_type != EXPECTED_TYPES["contactPoint"]:
            console.warning(
                f"Unexpected contactPoint @type '{contact_type}' (expected"
                f" '{EXPECTED_TYPES['contactPoint']}') in record {identifier}"
            )


def parse_files(distributions: list, identifier: str = "") -> list[EcudoFile]:
    """
    Parse distribution array into FileInfo list.

    Args:
        distributions: List of distribution dicts from JSON-LD
        identifier: Record identifier for logging context

    Returns:
        List of FileInfo objects (may be empty)
    """
    urls: list[str] = []
    for dist in distributions:
        # Validate distribution @type
        dist_type = dist.get("@type")
        if dist_type and dist_type != EXPECTED_TYPES["distribution"]:
            console.warning(
                f"Unexpected distribution @type '{dist_type}' (expected"
                f" '{EXPECTED_TYPES['distribution']}') in record {identifier}"
            )

        url = dist.get("downloadURL")
        if not url:
            continue

        urls.append(url)

    paths = resolve_path_collisions(urls)
    return [EcudoFile(path=p, url=u) for p, u in zip(paths, urls)]


def parse_publisher(publisher_data, identifier: str = "") -> str:
    """
    Parse publisher field which can be dict or string.

    Args:
        publisher_data: Publisher field from JSON-LD (dict, str, or None)
        identifier: Record identifier for logging context

    Returns:
        Publisher name string
    """
    if not publisher_data:
        return "Unknown Publisher"

    if isinstance(publisher_data, dict):
        return publisher_data.get("name", "Unknown Publisher")

    if isinstance(publisher_data, str):
        return publisher_data

    console.warning(
        f"Unexpected publisher type {type(publisher_data).__name__} in record"
        f" {identifier}"
    )
    return "Unknown Publisher"
