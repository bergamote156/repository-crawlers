"""
OpenAIRE Metadata Serializer

Generates OpenAIRE-compliant XML metadata based on:
OpenAIRE Guidelines for Literature Repository Managers v4.0.0
https://openaire-guidelines-for-literature-repository-managers.readthedocs.io/en/v4.0.0/
"""

from datetime import datetime

from ecudo.models.record import EcudoRecord
from ecudo.serializers.base import MetadataSerializer


class OpenAIRESerializer(MetadataSerializer):
    """
    OpenAIRE v4.0 XML metadata serializer.

    Generates XML compliant with OpenAIRE Guidelines for Literature
    Repository Managers v4.0.0.

    Mandatory properties (M):
        - datacite:title
        - datacite:creator
        - datacite:date (Publication Date)
        - oaire:resourceType
        - datacite:identifier (Resource Identifier)
        - datacite:rights (Access Rights)

    Mandatory if Applicable (MA):
        - dc:language
        - dc:publisher
        - dc:description
        - datacite:subject
        - oaire:file (File Location)
    """

    @property
    def format_name(self) -> str:
        return "OpenAIRE v4.0"

    @property
    def content_type(self) -> str:
        return "application/xml"

    def serialize(self, record: EcudoRecord) -> str:
        """
        Serialize EcudoRecord to OpenAIRE XML.

        Args:
            record: Structured dataset record

        Returns:
            OpenAIRE-compliant XML string
        """
        language_code = self._normalize_language_code(record.language)
        publication_date = record.issued or datetime.now().strftime("%Y-%m-%d")
        resource_type_uri = self._infer_coar_resource_type(record)

        # Use publisher as creator (organizational)
        creator_name = record.publisher

        # Build XML
        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<resource xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"',
            '  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
            '  xmlns:dc="http://purl.org/dc/elements/1.1/"',
            '  xmlns:dcterms="http://purl.org/dc/terms/"',
            '  xmlns:datacite="http://datacite.org/schema/kernel-4"',
            '  xmlns:oaire="http://namespace.openaire.eu/schema/oaire/"',
            '  xsi:schemaLocation="http://namespace.openaire.eu/schema/oaire/ https://www.openaire.eu/schema/repo-lit/4.0/openaire.xsd">',
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
            "  <!-- 10. Publication Date (M) -->",
            "  <datacite:dates>",
            f'    <datacite:date dateType="Issued">{publication_date}</datacite:date>',
            "  </datacite:dates>",
            "",
            "  <!-- 9. Publisher (MA) -->",
            f"  <dc:publisher>{_escape_xml(record.publisher)}</dc:publisher>",
            "",
            "  <!-- 11. Resource Type (M) - COAR Resource Type Vocabulary -->",
            f'  <oaire:resourceType resourceTypeGeneral="dataset" uri="{resource_type_uri}">dataset</oaire:resourceType>',
            "",
            "  <!-- 14. Resource Identifier (M) -->",
            '  <datacite:identifier identifierType="URN">',
            f"    {_escape_xml(record.identifier)}",
            "  </datacite:identifier>",
            "",
            "  <!-- 15. Access Rights (M) - COAR Access Rights Vocabulary -->",
            '  <datacite:rights rightsURI="http://purl.org/coar/access_right/c_abf2">open access</datacite:rights>',
            "",
            "  <!-- 8. Language (MA) -->",
            f"  <dc:language>{language_code}</dc:language>",
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
            geo_xml = self._build_geo_location_xml(record.spatial)
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
                xml_lines.append(
                    f'  <oaire:file accessRightsURI="http://purl.org/coar/access_right/c_abf2">{_escape_xml(file_info.url)}</oaire:file>'
                )

        xml_lines.append("</resource>")

        return "\n".join(xml_lines)

    @staticmethod
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

    @staticmethod
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

            if url_lower.endswith((".pdf",)):
                return "http://purl.org/coar/resource_type/c_18cf"  # text

            if url_lower.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff")):
                return "http://purl.org/coar/resource_type/c_c513"  # image

        # Default to dataset
        return "http://purl.org/coar/resource_type/c_ddb1"

    @staticmethod
    def _build_geo_location_xml(spatial: str) -> list[str]:
        """
        Build geo location XML from spatial string.

        Args:
            spatial: Spatial string in format "lon1,lat1,lon2,lat2"

        Returns:
            List of XML lines or empty list if parsing fails
        """
        try:
            coords = [float(x.strip()) for x in spatial.split(",")]
            if len(coords) == 4:
                return [
                    "",
                    "  <!-- 21. Geo Location (O) -->",
                    "  <datacite:geoLocations>",
                    "    <datacite:geoLocation>",
                    "      <datacite:geoLocationBox>",
                    f"        <datacite:westBoundLongitude>{coords[0]}</datacite:westBoundLongitude>",
                    f"        <datacite:eastBoundLongitude>{coords[2]}</datacite:eastBoundLongitude>",
                    f"        <datacite:southBoundLatitude>{coords[1]}</datacite:southBoundLatitude>",
                    f"        <datacite:northBoundLatitude>{coords[3]}</datacite:northBoundLatitude>",
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
