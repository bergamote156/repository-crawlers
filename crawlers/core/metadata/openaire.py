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
from typing import Callable, Protocol, Tuple

from crawlers.core import output
from crawlers.core.abc.metadata import MetadataBuilder

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


class DatasetFile(Protocol):
    """Dataset file object required properties by OpenAIREBuilder."""

    url: str


class Dataset(Protocol):
    """Dataset object required properties by OpenAIREBuilder."""

    identifier: str
    title: str
    description: str
    publisher: str
    issued: str  # publication date
    files: list[DatasetFile]
    language: str
    keywords: list[str]
    access_level: str
    spatial: str | None
    temporal: str | None


@dataclass
class OpenAIREContext:
    """Context object passed to section builders."""

    dataset: Dataset
    language_code: str
    rights_uri: str
    rights_label: str


class OpenAIREBuilder(MetadataBuilder[Dataset]):
    """
    Base OpenAIRE v4.0 metadata generator.

    Can be extended by plugins to add custom sections or modify existing ones.
    """

    def build(self, dataset: Dataset) -> str:
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
        ctx = self._build_context(dataset)

        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f"<oaire:resource {XML_NAMESPACES}>",
        ]

        for section_builder in self.get_sections():
            section_lines = section_builder(ctx)
            if section_lines:
                # Add spacing between sections if previous one wasn't empty
                if xml_lines and xml_lines[-1] != "":
                    xml_lines.append("")
                xml_lines.extend(section_lines)

        xml_lines.append("")
        xml_lines.append("</oaire:resource>")

        return "\n".join(xml_lines)

    def get_sections(self) -> list[Callable[[OpenAIREContext], list[str]]]:
        """
        Get the list of section builder methods.

        Override specific methods or this list to customize generation.

        Returns:
            List of callables that take context and return list of XML lines
        """
        return [
            self.build_title_section,
            self.build_creator_section,
            self.build_language_section,
            self.build_publisher_section,
            self.build_publication_date_section,
            self.build_resource_type_section,
            self.build_description_section,
            self.build_identifier_section,
            self.build_access_rights_section,
            self.build_subjects_section,
            self.build_temporal_section,
            self.build_geo_location_section,
            self.build_files_section,
        ]

    # --- Section Builders ---

    def build_title_section(self, ctx: OpenAIREContext) -> list[str]:
        return [
            "  <!-- 1. Title (M) -->",
            "  <datacite:titles>",
            f'    <datacite:title xml:lang="{ctx.language_code}">',
            f"      {self._escape_xml(ctx.dataset.title)}",
            "    </datacite:title>",
            "  </datacite:titles>",
        ]

    def build_creator_section(self, ctx: OpenAIREContext) -> list[str]:
        return [
            "  <!-- 2. Creator (M) -->",
            "  <datacite:creators>",
            "    <datacite:creator>",
            '      <datacite:creatorName nameType="Organizational">',
            f"        {self._escape_xml(ctx.dataset.publisher)}",
            "      </datacite:creatorName>",
            "    </datacite:creator>",
            "  </datacite:creators>",
        ]

    def build_language_section(self, ctx: OpenAIREContext) -> list[str]:
        return [
            "  <!-- 8. Language (MA) -->",
            f"  <dc:language>{ctx.language_code}</dc:language>",
        ]

    def build_publisher_section(self, ctx: OpenAIREContext) -> list[str]:
        return [
            "  <!-- 9. Publisher (MA) -->",
            f"  <dc:publisher>{self._escape_xml(ctx.dataset.publisher)}</dc:publisher>",
        ]

    def build_publication_date_section(self, ctx: OpenAIREContext) -> list[str]:
        publication_date = ctx.dataset.issued or datetime.now().strftime("%Y-%m-%d")
        return [
            "  <!-- 10. Publication Date (M) -->",
            "  <datacite:dates>",
            f'    <datacite:date dateType="Issued">{publication_date}</datacite:date>',
            "  </datacite:dates>",
        ]

    def build_resource_type_section(self, ctx: OpenAIREContext) -> list[str]:
        resource_type_uri = self._infer_coar_resource_type(ctx.dataset)
        return [
            "  <!-- 11. Resource Type (M) - COAR Resource Type Vocabulary -->",
            f'  <oaire:resourceType resourceTypeGeneral="dataset" uri="{resource_type_uri}">',
            "    dataset",
            "  </oaire:resourceType>",
        ]

    def build_description_section(self, ctx: OpenAIREContext) -> list[str]:
        if not ctx.dataset.description:
            return []
        return [
            "  <!-- 12. Description (MA) -->",
            f'  <dc:description xml:lang="{ctx.language_code}">',
            f"    {self._escape_xml(ctx.dataset.description)}",
            "  </dc:description>",
        ]

    def build_identifier_section(self, ctx: OpenAIREContext) -> list[str]:
        return [
            "  <!-- 14. Resource Identifier (M) -->",
            '  <datacite:identifier identifierType="URN">',
            f"    {self._escape_xml(ctx.dataset.identifier)}",
            "  </datacite:identifier>",
        ]

    def build_access_rights_section(self, ctx: OpenAIREContext) -> list[str]:
        return [
            "  <!-- 15. Access Rights (M) - COAR Access Rights Vocabulary -->",
            f'  <datacite:rights rightsURI="{ctx.rights_uri}">',
            f"    {ctx.rights_label}",
            "  </datacite:rights>",
        ]

    def build_subjects_section(self, ctx: OpenAIREContext) -> list[str]:
        if not ctx.dataset.keywords:
            return []

        lines = [
            "  <!-- 17. Subject (MA) -->",
            "  <datacite:subjects>",
        ]
        for keyword in ctx.dataset.keywords[:20]:
            lines.append(
                f"    <datacite:subject>{self._escape_xml(keyword)}</datacite:subject>"
            )
        lines.append("  </datacite:subjects>")
        return lines

    def build_temporal_section(self, ctx: OpenAIREContext) -> list[str]:
        if not ctx.dataset.temporal:
            return []
        return [
            "  <!-- 19. Coverage (R) - Temporal -->",
            f"  <dc:coverage>{self._escape_xml(ctx.dataset.temporal)}</dc:coverage>",
        ]

    def build_geo_location_section(self, ctx: OpenAIREContext) -> list[str]:
        if not ctx.dataset.spatial:
            return []
        return self._build_geo_location_xml(ctx.dataset.spatial)

    def build_files_section(self, ctx: OpenAIREContext) -> list[str]:
        if not ctx.dataset.files:
            return []

        lines = ["  <!-- 23. File Location (MA) -->"]
        for file_info in ctx.dataset.files:
            mime_type = self._infer_mime_type(file_info.url)
            mime_attr = f' mimeType="{mime_type}"' if mime_type else ""
            lines.extend(
                [
                    f'  <oaire:file accessRightsURI="{ctx.rights_uri}"{mime_attr}>',
                    f"    {self._escape_xml(file_info.url)}",
                    "  </oaire:file>",
                ]
            )
        return lines

    # --- Helpers ---

    def _build_context(self, dataset: Dataset) -> OpenAIREContext:
        language_code = self._normalize_language_code(dataset.language)
        rights_uri, rights_label = self._get_access_rights(dataset.access_level)

        return OpenAIREContext(
            dataset=dataset,
            language_code=language_code,
            rights_uri=rights_uri,
            rights_label=rights_label,
        )

    def _escape_xml(self, text: str) -> str:
        """Escape special XML characters."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

    def _normalize_language_code(self, language: str) -> str:
        """Normalize language to ISO 639-1 code."""
        if not language:
            return "en"

        language_lower = language.lower().strip()
        language_map = {
            "english": "eng",
            "polish": "pol",
        }

        if language_lower in language_map:
            return language_map[language_lower]

        if len(language_lower) in (2, 3) and language_lower.isalpha():
            return language_lower

        output.warning(
            f"Unknown language '{language}', defaulting to 'en'. "
            "Consider extending language_map."
        )
        return "en"

    def _get_access_rights(self, access_level: str) -> Tuple[str, str]:
        """Map access level to COAR Access Rights."""
        if access_level in ACCESS_RIGHTS_MAP:
            return ACCESS_RIGHTS_MAP[access_level]

        output.warning(
            f"Unknown access_level '{access_level}', defaulting to 'open access'."
        )
        return DEFAULT_ACCESS_RIGHTS

    def _infer_coar_resource_type(self, dataset: Dataset) -> str:
        """Infer COAR Resource Type URI from dataset."""
        if dataset.files:
            url_lower = dataset.files[0].url.lower()
            if url_lower.endswith(".pdf"):
                return "http://purl.org/coar/resource_type/c_18cf"  # text
            if url_lower.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff")):
                return "http://purl.org/coar/resource_type/c_c513"  # image

        return "http://purl.org/coar/resource_type/c_ddb1"  # dataset

    def _infer_mime_type(self, url: str) -> str | None:
        """Infer MIME type from file extension."""
        url_lower = url.lower()
        for ext, mime in MIME_TYPES.items():
            if url_lower.endswith(ext):
                return mime
        return None

    def _build_geo_location_xml(self, spatial: str) -> list[str]:
        """Build geo location XML from spatial string."""
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
