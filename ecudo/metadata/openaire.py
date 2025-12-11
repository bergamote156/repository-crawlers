"""
OpenAIRE Metadata Generator

Generates OpenAIRE-compliant XML metadata based on:
OpenAIRE Guidelines for Literature Repository Managers v4.0.0
https://openaire-guidelines-for-literature-repository-managers.readthedocs.io/en/v4.0.0/
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass
from datetime import datetime
from typing import Tuple

from ecudo import output
from ecudo.models.ecudo import EcudoDataset

# Metadata format constants
FORMAT_NAME = "OpenAIRE v4.0"
CONTENT_TYPE = "application/xml"

# COAR Access Rights vocabulary mapping
# https://vocabularies.coar-repositories.org/access_rights/
ACCESS_RIGHTS_MAP = {
    "public": ("http://purl.org/coar/access_right/c_abf2", "open access"),
}
DEFAULT_ACCESS_RIGHTS = ACCESS_RIGHTS_MAP["public"]

# MIME type inference from file extensions
MIME_TYPES = {
    ".zip": "application/zip",
    ".tar": "application/x-tar",
    ".gz": "application/gzip",
    ".tar.gz": "application/gzip",
    ".tgz": "application/gzip",
    ".pdf": "application/pdf",
    ".csv": "text/csv",
    ".json": "application/json",
    ".xml": "application/xml",
    ".nc": "application/x-netcdf",
    ".hdf": "application/x-hdf",
    ".hdf5": "application/x-hdf5",
    ".h5": "application/x-hdf5",
    ".txt": "text/plain",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".geojson": "application/geo+json",
}

# XML namespace declarations
XML_NAMESPACES = (
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/" '
    'xmlns:dcterms="http://purl.org/dc/terms/" '
    'xmlns:datacite="http://datacite.org/schema/kernel-4" '
    'xmlns:oaire="http://namespace.openaire.eu/schema/oaire/" '
    'xsi:schemaLocation="http://namespace.openaire.eu/schema/oaire/ '
    'https://www.openaire.eu/schema/repo-lit/4.0/openaire.xsd"'
)


@dataclass
class _OpenAIREContext:
    dataset: EcudoDataset
    language_code: str
    rights_uri: str
    rights_label: str


def generate_xml(dataset: EcudoDataset) -> str:
    """
    Generate OpenAIRE-compliant XML metadata from EcudoDataset.

    OpenAIRE Guidelines v4.0 Mandatory properties:
        - datacite:title (M)
        - datacite:creator (M)
        - datacite:date - Publication Date (M)
        - oaire:resourceType (M)
        - datacite:identifier - Resource Identifier (M)
        - datacite:rights - Access Rights (M)

    Mandatory if Applicable (MA):
        - dc:language
        - dc:publisher
        - dc:description
        - datacite:subject
        - oaire:file - File Location

    Args:
        dataset: Structured dataset

    Returns:
        OpenAIRE-compliant XML string
    """
    ctx = _build_context(dataset)

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f"<oaire:resource {XML_NAMESPACES}>",
    ]

    sections_builders = [
        _build_title_section,
        _build_creator_section,
        _build_language_section,
        _build_publisher_section,
        _build_publication_date_section,
        _build_resource_type_section,
        _build_description_section,
        _build_identifier_section,
        _build_access_rights_section,
        _build_subjects_section,
        _build_temporal_coverage_section,
        _build_geo_location_section,
        _build_files_section,
    ]

    for section_builder in sections_builders:
        _append_section(xml_lines, section_builder(ctx))

    xml_lines.append("")
    xml_lines.append("</oaire:resource>")

    return "\n".join(xml_lines)


def _build_context(dataset: EcudoDataset) -> _OpenAIREContext:
    language_code = _normalize_language_code(dataset.language)
    rights_uri, rights_label = _get_access_rights(dataset.access_level)

    return _OpenAIREContext(
        dataset=dataset,
        language_code=language_code,
        rights_uri=rights_uri,
        rights_label=rights_label,
    )


def _normalize_language_code(language: str) -> str:
    """
    Normalize language to ISO 639-1 code.

    Args:
        language: Language name or code

    Returns:
        ISO 639-1 two-letter code
    """
    if not language:
        return "en"

    language_lower = language.lower().strip()

    # Common language name mappings
    language_map = {
        "english": "eng",
        "polish": "pol",
    }

    if language_lower in language_map:
        return language_map[language_lower]

    # If already a 2 or 3 letter code, return as-is
    if len(language_lower) in (2, 3) and language_lower.isalpha():
        return language_lower

    output.warning(
        "Unknown language"
        f" '{language}', defaulting to 'en'. Consider extending language_map."
    )
    return "en"


def _get_access_rights(access_level: str) -> Tuple[str, str]:
    """
    Map access level to COAR Access Rights vocabulary.

    Args:
        access_level: Access level from ECUDO dataset (e.g., "public", "restricted")

    Returns:
        Tuple of (rights_uri, rights_label)
    """
    if access_level in ACCESS_RIGHTS_MAP:
        return ACCESS_RIGHTS_MAP[access_level]

    # Log unknown access level and default to open access
    output.warning(
        "Unknown access_level"
        f" '{access_level}', defaulting to 'open access'. Consider adding mapping in"
        " ACCESS_RIGHTS_MAP."
    )
    return DEFAULT_ACCESS_RIGHTS


def _append_section(xml_lines: list[str], section_lines: list[str]) -> None:
    if not section_lines:
        return

    if xml_lines and xml_lines[-1] != "":
        xml_lines.append("")

    xml_lines.extend(section_lines)


def _build_title_section(ctx: _OpenAIREContext) -> list[str]:
    return [
        "  <!-- 1. Title (M) -->",
        "  <datacite:titles>",
        f'    <datacite:title xml:lang="{ctx.language_code}">',
        f"      {_escape_xml(ctx.dataset.title)}",
        "    </datacite:title>",
        "  </datacite:titles>",
    ]


def _build_creator_section(ctx: _OpenAIREContext) -> list[str]:
    return [
        "  <!-- 2. Creator (M) -->",
        "  <datacite:creators>",
        "    <datacite:creator>",
        '      <datacite:creatorName nameType="Organizational">',
        f"        {_escape_xml(ctx.dataset.publisher)}",
        "      </datacite:creatorName>",
        "    </datacite:creator>",
        "  </datacite:creators>",
    ]


def _build_language_section(ctx: _OpenAIREContext) -> list[str]:
    return [
        "  <!-- 8. Language (MA) -->",
        f"  <dc:language>{ctx.language_code}</dc:language>",
    ]


def _build_publisher_section(ctx: _OpenAIREContext) -> list[str]:
    return [
        "  <!-- 9. Publisher (MA) -->",
        f"  <dc:publisher>{_escape_xml(ctx.dataset.publisher)}</dc:publisher>",
    ]


def _build_publication_date_section(ctx: _OpenAIREContext) -> list[str]:
    publication_date = ctx.dataset.issued or datetime.now().strftime("%Y-%m-%d")

    return [
        "  <!-- 10. Publication Date (M) -->",
        "  <datacite:dates>",
        f'    <datacite:date dateType="Issued">{publication_date}</datacite:date>',
        "  </datacite:dates>",
    ]


def _build_resource_type_section(ctx: _OpenAIREContext) -> list[str]:
    resource_type_uri = _infer_coar_resource_type(ctx.dataset)

    return [
        "  <!-- 11. Resource Type (M) - COAR Resource Type Vocabulary -->",
        f'  <oaire:resourceType resourceTypeGeneral="dataset" uri="{resource_type_uri}">',
        "    dataset",
        "  </oaire:resourceType>",
    ]


def _infer_coar_resource_type(dataset: EcudoDataset) -> str:
    """
    Infer COAR Resource Type URI from dataset.

    Args:
        dataset: Dataset

    Returns:
        COAR Resource Type URI
    """
    # Check first file URL for extension hints
    if dataset.files:
        url_lower = dataset.files[0].url.lower()

        if url_lower.endswith(".pdf"):
            return "http://purl.org/coar/resource_type/c_18cf"  # text

        if url_lower.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff")):
            return "http://purl.org/coar/resource_type/c_c513"  # image

    # Default to dataset
    return "http://purl.org/coar/resource_type/c_ddb1"


def _build_description_section(ctx: _OpenAIREContext) -> list[str]:
    if not ctx.dataset.description:
        return []

    return [
        "  <!-- 12. Description (MA) -->",
        f'  <dc:description xml:lang="{ctx.language_code}">',
        f"    {_escape_xml(ctx.dataset.description)}",
        "  </dc:description>",
    ]


def _build_identifier_section(ctx: _OpenAIREContext) -> list[str]:
    return [
        "  <!-- 14. Resource Identifier (M) -->",
        '  <datacite:identifier identifierType="URN">',
        f"    {_escape_xml(ctx.dataset.identifier)}",
        "  </datacite:identifier>",
    ]


def _build_access_rights_section(ctx: _OpenAIREContext) -> list[str]:
    return [
        "  <!-- 15. Access Rights (M) - COAR Access Rights Vocabulary -->",
        f'  <datacite:rights rightsURI="{ctx.rights_uri}">',
        f"    {ctx.rights_label}",
        "  </datacite:rights>",
    ]


def _build_subjects_section(ctx: _OpenAIREContext) -> list[str]:
    if not ctx.dataset.keywords:
        return []

    lines = [
        "  <!-- 17. Subject (MA) -->",
        "  <datacite:subjects>",
    ]

    for keyword in ctx.dataset.keywords[:20]:
        lines.append(f"    <datacite:subject>{_escape_xml(keyword)}</datacite:subject>")

    lines.append("  </datacite:subjects>")
    return lines


def _build_temporal_coverage_section(ctx: _OpenAIREContext) -> list[str]:
    if not ctx.dataset.temporal:
        return []

    return [
        "  <!-- 19. Coverage (R) - Temporal -->",
        f"  <dc:coverage>{_escape_xml(ctx.dataset.temporal)}</dc:coverage>",
    ]


def _build_geo_location_section(ctx: _OpenAIREContext) -> list[str]:
    if not ctx.dataset.spatial:
        return []

    return _build_geo_location_xml(ctx.dataset.spatial)


def _build_geo_location_xml(spatial: str) -> list[str]:
    """
    Build geo location XML from spatial string.

    Args:
        spatial: Spatial string in format "westLon,southLat,eastLon,northLat"

    Returns:
        List of XML lines or empty list if parsing fails
    """
    try:
        coords = [float(x.strip()) for x in spatial.split(",")]
        if len(coords) == 4:
            west_lon, south_lat, east_lon, north_lat = coords
            return [
                "  <!-- 21. Geo Location (O) -->",
                "  <datacite:geoLocations>",
                "    <datacite:geoLocation>",
                "      <datacite:geoLocationBox>",
                f"        <datacite:westBoundLongitude>{west_lon}</datacite:westBoundLongitude>",
                f"        <datacite:eastBoundLongitude>{east_lon}</datacite:eastBoundLongitude>",
                f"        <datacite:southBoundLatitude>{south_lat}</datacite:southBoundLatitude>",
                f"        <datacite:northBoundLatitude>{north_lat}</datacite:northBoundLatitude>",
                "      </datacite:geoLocationBox>",
                "    </datacite:geoLocation>",
                "  </datacite:geoLocations>",
            ]
    except (ValueError, AttributeError):
        pass

    return []


def _build_files_section(ctx: _OpenAIREContext) -> list[str]:
    if not ctx.dataset.files:
        return []

    lines = ["  <!-- 23. File Location (MA) -->"]

    for file_info in ctx.dataset.files:
        mime_type = _infer_mime_type(file_info.url)
        mime_attr = f' mimeType="{mime_type}"' if mime_type else ""
        lines.extend(
            [
                f'  <oaire:file accessRightsURI="{ctx.rights_uri}"{mime_attr}>',
                f"    {_escape_xml(file_info.url)}",
                "  </oaire:file>",
            ]
        )

    return lines


def _infer_mime_type(url: str) -> str | None:
    """
    Infer MIME type from file URL extension.

    Args:
        url: File download URL

    Returns:
        MIME type string or None if cannot be determined
    """
    url_lower = url.lower()

    # Check for compound extensions first
    for ext, mime in MIME_TYPES.items():
        if url_lower.endswith(ext):
            return mime

    return None


def _escape_xml(text: str) -> str:
    """Escape special XML characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
