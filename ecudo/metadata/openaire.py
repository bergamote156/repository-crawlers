"""
OpenAIRE Metadata Generator

Generates OpenAIRE-compliant XML metadata based on:
OpenAIRE Guidelines for Literature Repository Managers v4.0.0
https://openaire-guidelines-for-literature-repository-managers.readthedocs.io/en/v4.0.0/
"""

from datetime import datetime
from typing import Tuple

from ecudo import output
from ecudo.models.record import EcudoRecord

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


def generate_xml(record: EcudoRecord) -> str:
    """
    Generate OpenAIRE-compliant XML metadata from EcudoRecord.

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
        record: Structured dataset record

    Returns:
        OpenAIRE-compliant XML string
    """
    language_code = _normalize_language_code(record.language)
    publication_date = record.issued or datetime.now().strftime("%Y-%m-%d")
    resource_type_uri = _infer_coar_resource_type(record)
    rights_uri, rights_label = _get_access_rights(record.access_level)

    # Use publisher as creator (organizational)
    creator_name = record.publisher

    # Build XML
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f"<oaire:resource {XML_NAMESPACES}>",
        "",
        "  <!-- 1. Title (M) -->",
        "  <datacite:titles>",
        f'    <datacite:title xml:lang="{language_code}">{_escape_xml(record.title)}</datacite:title>',
        "  </datacite:titles>",
        "",
        "  <!-- 2. Creator (M) -->",
        "  <datacite:creators>",
        "    <datacite:creator>",
        f'      <datacite:creatorName nameType="Organizational">{_escape_xml(creator_name)}</datacite:creatorName>',
        "    </datacite:creator>",
        "  </datacite:creators>",
        "",
        "  <!-- 8. Language (MA) -->",
        f"  <dc:language>{language_code}</dc:language>",
        "",
        "  <!-- 9. Publisher (MA) -->",
        f"  <dc:publisher>{_escape_xml(record.publisher)}</dc:publisher>",
        "",
        "  <!-- 10. Publication Date (M) -->",
        "  <datacite:dates>",
        f'    <datacite:date dateType="Issued">{publication_date}</datacite:date>',
        "  </datacite:dates>",
        "",
        "  <!-- 11. Resource Type (M) - COAR Resource Type Vocabulary -->",
        f'  <oaire:resourceType resourceTypeGeneral="dataset" uri="{resource_type_uri}">dataset</oaire:resourceType>',
        "",
        "  <!-- 14. Resource Identifier (M) -->",
        f'  <datacite:identifier identifierType="URN">{_escape_xml(record.identifier)}</datacite:identifier>',
        "",
        "  <!-- 15. Access Rights (M) - COAR Access Rights Vocabulary -->",
        f'  <datacite:rights rightsURI="{rights_uri}">{rights_label}</datacite:rights>',
    ]

    # 12. Description (MA)
    if record.description:
        xml_lines.extend(
            [
                "",
                "  <!-- 12. Description (MA) -->",
                f'  <dc:description xml:lang="{language_code}">',
                f"    {_escape_xml(record.description)}",
                "  </dc:description>",
            ]
        )

    # 17. Subject (MA) - from keywords
    if record.keywords:
        xml_lines.extend(
            [
                "",
                "  <!-- 17. Subject (MA) -->",
                "  <datacite:subjects>",
            ]
        )
        for keyword in record.keywords[:20]:  # Limit to 20 keywords
            xml_lines.append(
                f"    <datacite:subject>{_escape_xml(keyword)}</datacite:subject>"
            )
        xml_lines.append("  </datacite:subjects>")

    # 19. Coverage (R) - temporal
    if record.temporal:
        xml_lines.extend(
            [
                "",
                "  <!-- 19. Coverage (R) - Temporal -->",
                f"  <dc:coverage>{_escape_xml(record.temporal)}</dc:coverage>",
            ]
        )

    # 21. Geo Location (O) - from spatial
    if record.spatial:
        geo_xml = _build_geo_location_xml(record.spatial)
        if geo_xml:
            xml_lines.extend(geo_xml)

    # 23. File Location (MA)
    if record.files:
        xml_lines.extend(
            [
                "",
                "  <!-- 23. File Location (MA) -->",
            ]
        )
        for file_info in record.files:
            mime_type = _infer_mime_type(file_info.url)
            mime_attr = f' mimeType="{mime_type}"' if mime_type else ""
            xml_lines.append(
                f'  <oaire:file accessRightsURI="{rights_uri}"{mime_attr}>{_escape_xml(file_info.url)}</oaire:file>'
            )

    xml_lines.append("")
    xml_lines.append("</oaire:resource>")

    return "\n".join(xml_lines)


def _get_access_rights(access_level: str) -> Tuple[str, str]:
    """
    Map access level to COAR Access Rights vocabulary.

    Args:
        access_level: Access level from ECUDO record (e.g., "public", "restricted")

    Returns:
        Tuple of (rights_uri, rights_label)
    """
    if access_level in ACCESS_RIGHTS_MAP:
        return ACCESS_RIGHTS_MAP[access_level]

    # Log unknown access level and default to open access
    output.warning(
        "Unknown access_level '%s', defaulting to 'open access'. "
        "Consider adding mapping in ACCESS_RIGHTS_MAP.",
        access_level,
    )
    return DEFAULT_ACCESS_RIGHTS


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
        "english": "en",
        "polish": "pl",
        "german": "de",
        "french": "fr",
        "spanish": "es",
        "italian": "it",
        "portuguese": "pt",
        "dutch": "nl",
        "czech": "cs",
        "slovak": "sk",
        "hungarian": "hu",
        "romanian": "ro",
        "bulgarian": "bg",
        "greek": "el",
        "swedish": "sv",
        "finnish": "fi",
        "danish": "da",
        "norwegian": "no",
    }

    if language_lower in language_map:
        return language_map[language_lower]

    # If already a 2 or 3 letter code, return as-is
    if len(language_lower) in (2, 3) and language_lower.isalpha():
        return language_lower

    return "en"


def _infer_coar_resource_type(record: EcudoRecord) -> str:
    """
    Infer COAR Resource Type URI from record.

    Args:
        record: Dataset record

    Returns:
        COAR Resource Type URI
    """
    # Check first file URL for extension hints
    if record.files:
        url_lower = record.files[0].url.lower()

        if url_lower.endswith(".pdf"):
            return "http://purl.org/coar/resource_type/c_18cf"  # text

        if url_lower.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff")):
            return "http://purl.org/coar/resource_type/c_c513"  # image

    # Default to dataset
    return "http://purl.org/coar/resource_type/c_ddb1"


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
                "",
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


def _escape_xml(text: str) -> str:
    """Escape special XML characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
