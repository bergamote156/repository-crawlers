"""
Ecudo Parser.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from contextlib import suppress
from urllib.parse import urlparse

from crawlers.core.ui import console
from crawlers.core.processors.fetchers import Parser
from crawlers.plugins.ecudo.models import EcudoDataset, EcudoFile

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
            validate_structure(raw, identifier)
            dataset = self._parse_record(raw, identifier)
            return dataset
        except Exception as e:  # pylint: disable=broad-except
            console.warning(f"Failed to parse record {identifier}: {e}")
            return None

    def _parse_record(self, raw: dict, identifier: str) -> None | EcudoDataset:
        """Internal parsing logic."""

        # Extract files (distribution)
        distributions = raw.get("distribution", [])
        if not distributions:
            console.debug(f"Skipping {identifier}: no distribution URLs")
            return None

        files = parse_files(distributions, identifier)
        if not files:
            console.debug(f"Skipping {identifier}: no valid download URLs")
            return None

        publisher = parse_publisher(raw.get("publisher"), identifier)

        return EcudoDataset(
            identifier=identifier,
            title=raw.get("title", "Untitled Dataset"),
            description=raw.get("description", ""),
            publisher=publisher,
            language=raw.get("language", "en"),
            keywords=raw.get("keywords", []),
            files=files,
            issued=raw.get("issued", raw.get("modified", "")),
            modified=raw.get("modified"),
            spatial=raw.get("spatial"),
            temporal=raw.get("temporal"),
            access_level=raw.get("accessLevel", "public"),
            _raw=raw,
        )


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
    files = []
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

        files.append(
            EcudoFile(
                name=extract_filename(url),
                url=url,
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

    console.warning(
        f"Unexpected publisher type {type(publisher_data).__name__} in record"
        f" {identifier}"
    )
    return "Unknown Publisher"


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
