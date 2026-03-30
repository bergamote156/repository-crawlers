"""
DataCite Metadata Generator

Generates DataCite Kernel 4.5 compliant XML metadata.
https://schema.datacite.org/meta/kernel-4.5/
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Protocol, Sequence
from xml.dom import minidom

from crawlers.core.metadata import MetadataBuilder

# XML namespace declarations
DATACITE_NS = "http://datacite.org/schema/kernel-4"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOCATION = (
    "http://datacite.org/schema/kernel-4 "
    "http://schema.datacite.org/meta/kernel-4.5/metadata.xsd"
)

# Register namespaces to avoid ns0/ns1 prefixes in output
ET.register_namespace("", DATACITE_NS)
ET.register_namespace("xsi", XSI_NS)


class DataCiteFile(Protocol):
    """File object required properties by DataCiteBuilder."""

    # pylint: disable=too-few-public-methods

    url: str


class DataCiteDataset(Protocol):
    """Dataset object required properties by DataCiteBuilder."""

    # pylint: disable=too-few-public-methods

    identifier: str
    title: str
    datetime: str | None
    geometry: dict | None
    files: Sequence[DataCiteFile]
    self_link: str | None


@dataclass
class DataCiteContext:
    """Context object passed to section builders."""

    dataset: DataCiteDataset
    publication_year: int


class DataCiteBuilder(MetadataBuilder[DataCiteDataset]):
    """
    DataCite Kernel 4.5 metadata generator.

    Produces XML compliant with DataCite schema. Can be extended by
    subclasses to customize section builders.
    """

    # Default values - can be overridden by subclasses
    creator_name: str = "Unknown Creator"
    publisher_name: str = "Unknown Publisher"
    resource_type_general: str = "Dataset"
    resource_type_value: str = "dataset"
    default_subjects: list[str] = []
    default_description: str = ""
    default_rights: str = ""

    def build(self, dataset: DataCiteDataset) -> str:
        """
        Generate DataCite-compliant XML metadata.

        DataCite Kernel 4.5 Mandatory properties:
            - identifier (M)
            - creators (M)
            - titles (M)
            - publisher (M)
            - publicationYear (M)
            - resourceType (M)

        Optional properties included:
            - subjects (R)
            - dates (R)
            - geoLocations (R)
            - descriptions (R)
            - relatedIdentifiers (R)
            - rightsList (O)

        Args:
            dataset: Dataset with required properties

        Returns:
            DataCite-compliant XML string
        """
        ctx = self._build_context(dataset)
        root = self._create_root()

        for section_builder in self.get_sections():
            section_builder(root, ctx)

        return self._prettify(root)

    def get_sections(
        self,
    ) -> list[Callable[[ET.Element, DataCiteContext], None]]:
        """
        Get the list of section builder methods.

        Override specific methods or this list to customize generation.

        Returns:
            List of callables that take (root, context) and modify root
        """
        return [
            self.build_identifier_section,
            self.build_creators_section,
            self.build_titles_section,
            self.build_publisher_section,
            self.build_publication_year_section,
            self.build_resource_type_section,
            self.build_subjects_section,
            self.build_dates_section,
            self.build_geo_locations_section,
            self.build_descriptions_section,
            self.build_related_identifiers_section,
            self.build_rights_section,
        ]

    # --- Section Builders ---

    def build_identifier_section(self, root: ET.Element, ctx: DataCiteContext) -> None:
        """Build identifier section."""
        identifier = ET.SubElement(root, "identifier", {"identifierType": "DOI"})
        identifier.text = f"10.12345/{ctx.dataset.identifier}"

    def build_creators_section(
        self, root: ET.Element, ctx: DataCiteContext  # pylint: disable=unused-argument
    ) -> None:
        """Build creators section."""
        creators = ET.SubElement(root, "creators")
        creator = ET.SubElement(creators, "creator")
        creator_name = ET.SubElement(creator, "creatorName")
        creator_name.text = self.creator_name

    def build_titles_section(self, root: ET.Element, ctx: DataCiteContext) -> None:
        """Build titles section."""
        titles = ET.SubElement(root, "titles")
        title = ET.SubElement(titles, "title")
        title.text = ctx.dataset.title

    def build_publisher_section(
        self, root: ET.Element, ctx: DataCiteContext  # pylint: disable=unused-argument
    ) -> None:
        """Build publisher section."""
        publisher = ET.SubElement(root, "publisher")
        publisher.text = self.publisher_name

    def build_publication_year_section(
        self, root: ET.Element, ctx: DataCiteContext
    ) -> None:
        """Build publication year section."""
        pub_year = ET.SubElement(root, "publicationYear")
        pub_year.text = str(ctx.publication_year)

    def build_resource_type_section(
        self, root: ET.Element, ctx: DataCiteContext  # pylint: disable=unused-argument
    ) -> None:
        """Build resource type section."""
        resource_type = ET.SubElement(
            root,
            "resourceType",
            {"resourceTypeGeneral": self.resource_type_general},
        )
        resource_type.text = self.resource_type_value

    def build_subjects_section(
        self, root: ET.Element, ctx: DataCiteContext  # pylint: disable=unused-argument
    ) -> None:
        """Build subjects section."""
        if not self.default_subjects:
            return

        subjects = ET.SubElement(root, "subjects")
        for subj in self.default_subjects:
            subject = ET.SubElement(subjects, "subject")
            subject.text = subj

    def build_dates_section(self, root: ET.Element, ctx: DataCiteContext) -> None:
        """Build dates section."""
        if not ctx.dataset.datetime:
            return

        dates = ET.SubElement(root, "dates")
        date = ET.SubElement(dates, "date", {"dateType": "Collected"})
        date.text = ctx.dataset.datetime

    def build_geo_locations_section(
        self, root: ET.Element, ctx: DataCiteContext
    ) -> None:
        """Build geoLocations section from GeoJSON geometry."""
        geom = ctx.dataset.geometry
        if not geom or geom.get("type") != "Polygon":
            return

        coords = geom.get("coordinates", [[]])
        if not coords or not coords[0]:
            return

        geolocs = ET.SubElement(root, "geoLocations")
        geoloc = ET.SubElement(geolocs, "geoLocation")
        polygon = ET.SubElement(geoloc, "geoLocationPolygon")

        for lon, lat in coords[0]:
            point = ET.SubElement(polygon, "polygonPoint")
            point_lon = ET.SubElement(point, "pointLongitude")
            point_lon.text = str(lon)
            point_lat = ET.SubElement(point, "pointLatitude")
            point_lat.text = str(lat)

    def build_descriptions_section(
        self, root: ET.Element, ctx: DataCiteContext  # pylint: disable=unused-argument
    ) -> None:
        """Build descriptions section."""
        if not self.default_description:
            return

        descriptions = ET.SubElement(root, "descriptions")
        description = ET.SubElement(
            descriptions, "description", {"descriptionType": "Abstract"}
        )
        description.text = self.default_description

    def build_related_identifiers_section(
        self, root: ET.Element, ctx: DataCiteContext
    ) -> None:
        """Build relatedIdentifiers section."""
        if not ctx.dataset.self_link:
            return

        related = ET.SubElement(root, "relatedIdentifiers")
        related_id = ET.SubElement(
            related,
            "relatedIdentifier",
            {
                "relatedIdentifierType": "URL",
                "relationType": "IsSupplementTo",
            },
        )
        related_id.text = ctx.dataset.self_link

    def build_rights_section(
        self, root: ET.Element, ctx: DataCiteContext  # pylint: disable=unused-argument
    ) -> None:
        """Build rightsList section."""
        if not self.default_rights:
            return

        rights_list = ET.SubElement(root, "rightsList")
        rights = ET.SubElement(rights_list, "rights")
        rights.text = self.default_rights

    # --- Helpers ---

    def _build_context(self, dataset: DataCiteDataset) -> DataCiteContext:
        """Build context object for section builders."""
        return DataCiteContext(
            dataset=dataset,
            publication_year=datetime.now(UTC).year,
        )

    def _create_root(self) -> ET.Element:
        """Create the root resource element with proper namespaces."""
        # Following DataCite schema - root element with schemaLocation
        return ET.Element(
            "resource",
            {
                f"{{{XSI_NS}}}schemaLocation": SCHEMA_LOCATION,
            },
        )

    def _prettify(self, elem: ET.Element) -> str:
        """Convert ElementTree to pretty-printed XML string."""
        rough = ET.tostring(elem, encoding="unicode")
        reparsed = minidom.parseString(rough)
        return reparsed.toprettyxml(indent="  ")
