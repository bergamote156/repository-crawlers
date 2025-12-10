"""Utilities for parsing eCUDO JSON-LD responses into EcudoRecord objects."""

from contextlib import suppress
from typing import Optional, Tuple
from urllib.parse import urlparse

from ecudo import output
from ecudo.models.record import EcudoRecord, FileInfo

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
    "identifier",
    "title",
    "description",
    "publisher",
    "issued",
    "modified",
    "language",
    "accessLevel",
    "keywords",
    "spatial",
    "temporal",
    "contactPoint",
    "distribution",
}

# Known accessLevel values
KNOWN_ACCESS_LEVELS = {"public"}


def parse_record(raw: dict) -> Optional[EcudoRecord]:
    """
    Parse raw eCUDO JSON-LD to structured EcudoRecord.

    Args:
        raw: Raw JSON-LD dict from eCUDO API

    Returns:
        EcudoRecord if valid, None if record is invalid/incomplete
    """
    identifier = raw.get("identifier")
    if not identifier:
        output.debug("Skipping record: missing identifier")
        return None

    # Validate structure and log warnings for unexpected values
    _validate_structure(raw, identifier)

    distributions = raw.get("distribution", [])
    if not distributions:
        output.debug(f"Skipping {identifier}: no distribution URLs")
        return None

    files = parse_files(distributions, identifier)
    if not files:
        output.debug(f"Skipping {identifier}: no valid download URLs")
        return None

    publisher = parse_publisher(raw.get("publisher"), identifier)
    contact_name, contact_email = parse_contact_point(
        raw.get("contactPoint"), identifier
    )

    try:
        return EcudoRecord(
            identifier=identifier,
            title=raw.get("title", "Untitled Dataset"),
            description=raw.get("description", ""),
            publisher=publisher,
            issued=raw.get("issued", raw.get("modified", "")),
            language=raw.get("language", "en"),
            keywords=raw.get("keywords", []),
            files=files,
            spatial=raw.get("spatial"),
            temporal=raw.get("temporal"),
            access_level=raw.get("accessLevel", "public"),
            contact_name=contact_name,
            contact_email=contact_email,
            modified=raw.get("modified"),
            _raw=raw,
        )
    except ValueError as e:
        output.debug(f"Skipping {identifier}: {e}")
        return None


def _validate_structure(raw: dict, identifier: str) -> None:
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
        output.warning(
            f"Unexpected root @type '{root_type}' (expected '{EXPECTED_TYPES['root']}')"
            f" in record {identifier}"
        )

    # Check for unknown root fields
    unknown_fields = set(raw.keys()) - KNOWN_ROOT_FIELDS
    if unknown_fields:
        output.warning(
            f"Unknown fields {sorted(unknown_fields)} in record {identifier} - consider"
            " updating parser"
        )

    # Check accessLevel
    access_level = raw.get("accessLevel")
    if access_level and access_level not in KNOWN_ACCESS_LEVELS:
        output.warning(
            f"Unknown accessLevel '{access_level}' in record {identifier} - verify COAR"
            " mapping"
        )

    # Check publisher @type if present
    publisher = raw.get("publisher")
    if isinstance(publisher, dict):
        pub_type = publisher.get("@type")
        if pub_type and pub_type != EXPECTED_TYPES["publisher"]:
            output.warning(
                f"Unexpected publisher @type '{pub_type}' (expected"
                f" '{EXPECTED_TYPES['publisher']}') in record {identifier}"
            )

    # Check contactPoint @type if present
    contact = raw.get("contactPoint")
    if isinstance(contact, dict):
        contact_type = contact.get("@type")
        if contact_type and contact_type != EXPECTED_TYPES["contactPoint"]:
            output.warning(
                f"Unexpected contactPoint @type '{contact_type}' (expected"
                f" '{EXPECTED_TYPES['contactPoint']}') in record {identifier}"
            )


def parse_files(distributions: list, identifier: str = "") -> list[FileInfo]:
    """
    Parse distribution array into FileInfo list.

    Args:
        distributions: List of distribution dicts from JSON-LD
        identifier: Record identifier for logging context

    Returns:
        List of FileInfo objects (may be empty)
    """
    files = []
    for dist in distributions:
        # Validate distribution @type
        dist_type = dist.get("@type")
        if dist_type and dist_type != EXPECTED_TYPES["distribution"]:
            output.warning(
                f"Unexpected distribution @type '{dist_type}' (expected"
                f" '{EXPECTED_TYPES['distribution']}') in record {identifier}"
            )

        url = dist.get("downloadURL")
        if not url:
            continue

        files.append(
            FileInfo(
                name=extract_filename(url),
                url=url,
                format=dist.get("format"),
            )
        )

    return files


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

    output.warning(
        f"Unexpected publisher type {type(publisher_data).__name__} in record"
        f" {identifier}"
    )
    return "Unknown Publisher"


def parse_contact_point(
    contact_data, identifier: str = ""
) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse contactPoint field to extract contact name and email.

    Args:
        contact_data: ContactPoint field from JSON-LD (dict or None)
        identifier: Record identifier for logging context

    Returns:
        Tuple of (contact_name, contact_email), both may be None
    """
    if not contact_data:
        return None, None

    if not isinstance(contact_data, dict):
        output.warning(
            f"Unexpected contactPoint type {type(contact_data).__name__} in record"
            f" {identifier}"
        )
        return None, None

    contact_name = contact_data.get("fn")
    contact_email = contact_data.get("hasEmail")

    return contact_name, contact_email


def extract_filename(url: str) -> str:
    """
    Extract filename from URL.

    Args:
        url: Download URL

    Returns:
        Extracted filename or "data.bin" as fallback
    """
    with suppress(ValueError, AttributeError, TypeError):
        path = urlparse(url).path
        if path:
            filename = path.split("/")[-1]
            if filename:
                return filename

    # Gracefully fall through to default filename
    return "data.bin"
