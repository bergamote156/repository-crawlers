"""
OpenAIRE Metadata Builder.

Generates OpenAIRE-compliant XML metadata based on:
OpenAIRE Guidelines for Literature Repository Managers v4.0.0
https://openaire-guidelines-for-literature-repository-managers.readthedocs.io/en/v4.0.0/

The builder consumes a structured `OpenAIRERecord` describing a single
resource. Plugins are responsible for converting their domain dataset into a
record — keeping the builder ignorant of source-specific quirks (defaults,
fallbacks, ad-hoc parsing).
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum

from crawlers.core.metadata import MetadataBuilder

# --- Namespaces ---------------------------------------------------------------

NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
NS_DC = "http://purl.org/dc/elements/1.1/"
NS_DCTERMS = "http://purl.org/dc/terms/"
NS_DATACITE = "http://datacite.org/schema/kernel-4"
NS_OAIRE = "http://namespace.openaire.eu/schema/oaire/"
NS_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"

_SCHEMA_LOCATION = (
    "http://namespace.openaire.eu/schema/oaire/ "
    "https://www.openaire.eu/schema/repo-lit/4.0/openaire.xsd"
)


def _register_namespaces() -> None:
    """Bind our preferred prefixes in ElementTree's global namespace map."""
    ET.register_namespace("xsi", NS_XSI)
    ET.register_namespace("dc", NS_DC)
    ET.register_namespace("dcterms", NS_DCTERMS)
    ET.register_namespace("datacite", NS_DATACITE)
    ET.register_namespace("oaire", NS_OAIRE)
    ET.register_namespace("rdf", NS_RDF)


_register_namespaces()

_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


def _q(ns: str, tag: str) -> str:
    """Build an ElementTree Clark-notation tag."""
    return f"{{{ns}}}{tag}"


# --- Vocabularies -------------------------------------------------------------


class AccessRights(Enum):
    """COAR Access Rights vocabulary (https://vocabularies.coar-repositories.org/access_rights/)."""

    OPEN = ("http://purl.org/coar/access_right/c_abf2", "open access")
    EMBARGOED = ("http://purl.org/coar/access_right/c_f1cf", "embargoed access")
    RESTRICTED = ("http://purl.org/coar/access_right/c_16ec", "restricted access")
    METADATA_ONLY = ("http://purl.org/coar/access_right/c_14cb", "metadata only access")

    @property
    def uri(self) -> str:
        """COAR concept URI."""
        return self.value[0]

    @property
    def label(self) -> str:
        """Human-readable English label."""
        return self.value[1]


class ResourceType(Enum):
    """COAR Resource Type vocabulary (subset)."""

    DATASET = ("http://purl.org/coar/resource_type/c_ddb1", "dataset")
    TEXT = ("http://purl.org/coar/resource_type/c_18cf", "text")
    IMAGE = ("http://purl.org/coar/resource_type/c_c513", "image")

    @property
    def uri(self) -> str:
        """COAR concept URI."""
        return self.value[0]

    @property
    def label(self) -> str:
        """Human-readable English label."""
        return self.value[1]


# --- Record model -------------------------------------------------------------


@dataclass
class BoundingBox:
    """Geographic bounding box in WGS84 decimal degrees."""

    west: float
    south: float
    east: float
    north: float


@dataclass
class FileLocation:
    """A downloadable file referenced by an OpenAIRE record."""

    url: str
    mime_type: str | None = None


@dataclass
# pylint: disable=too-many-instance-attributes
class OpenAIRERecord:
    """
    Structured input for `OpenAIREBuilder`.

    Required fields (M / "Mandatory" in OpenAIRE Guidelines v4.0) have no
    default — the dataclass constructor enforces their presence. Optional
    fields default to 'None' / empty collections; sections corresponding
    to absent fields are not emitted.
    """

    # Mandatory (M)
    title: str
    creator: str
    identifier: str
    publication_date: str  # ISO 8601 date string
    access_rights: AccessRights
    resource_type: ResourceType = ResourceType.DATASET

    # Mandatory if Applicable (MA)
    language: str | None = None  # ISO 639-1/3 code; section omitted if None
    publisher: str | None = None
    description: str | None = None
    subjects: list[str] = field(default_factory=list)
    files: list[FileLocation] = field(default_factory=list)

    # Recommended / Optional (R/O)
    temporal_coverage: str | None = None
    spatial_coverage: BoundingBox | None = None


# --- Builder ------------------------------------------------------------------


# pylint: disable=too-few-public-methods
class OpenAIREBuilder(MetadataBuilder[OpenAIRERecord]):
    """Render an `OpenAIRERecord` to an OpenAIRE v4.0 XML string."""

    def build(self, record: OpenAIRERecord) -> str:
        root = ET.Element(
            _q(NS_OAIRE, "resource"),
            {_q(NS_XSI, "schemaLocation"): _SCHEMA_LOCATION},
        )

        # Order matches the OpenAIRE Guidelines section numbering for
        # readability. Sections that depend on optional fields no-op when
        # the field is unset.
        _add_title(root, record)
        _add_creator(root, record)
        _add_language(root, record)
        _add_publisher(root, record)
        _add_publication_date(root, record)
        _add_resource_type(root, record)
        _add_description(root, record)
        _add_identifier(root, record)
        _add_access_rights(root, record)
        _add_subjects(root, record)
        _add_temporal_coverage(root, record)
        _add_spatial_coverage(root, record)
        _add_files(root, record)

        ET.indent(root, space="  ")
        return ET.tostring(
            root, encoding="unicode", xml_declaration=True, short_empty_elements=False
        )


# --- Section builders (private) ----------------------------------------------
#
# Each function appends to 'root' if its corresponding record field is
# populated, and is a no-op otherwise. They intentionally use the
# ElementTree imperative style — keeping each section to a handful of lines
# is preferred over factoring out a more abstract section framework.


def _add_title(root: ET.Element, record: OpenAIRERecord) -> None:
    """1. Title (M)."""
    titles = ET.SubElement(root, _q(NS_DATACITE, "titles"))
    title = ET.SubElement(titles, _q(NS_DATACITE, "title"))
    if record.language:
        title.set(_XML_LANG, record.language)
    title.text = record.title


def _add_creator(root: ET.Element, record: OpenAIRERecord) -> None:
    """2. Creator (M)."""
    creators = ET.SubElement(root, _q(NS_DATACITE, "creators"))
    creator = ET.SubElement(creators, _q(NS_DATACITE, "creator"))
    name = ET.SubElement(
        creator, _q(NS_DATACITE, "creatorName"), {"nameType": "Organizational"}
    )
    name.text = record.creator


def _add_language(root: ET.Element, record: OpenAIRERecord) -> None:
    """8. Language (MA)."""
    if not record.language:
        return
    el = ET.SubElement(root, _q(NS_DC, "language"))
    el.text = record.language


def _add_publisher(root: ET.Element, record: OpenAIRERecord) -> None:
    """9. Publisher (MA)."""
    if not record.publisher:
        return
    el = ET.SubElement(root, _q(NS_DC, "publisher"))
    el.text = record.publisher


def _add_publication_date(root: ET.Element, record: OpenAIRERecord) -> None:
    """10. Publication Date (M)."""
    dates = ET.SubElement(root, _q(NS_DATACITE, "dates"))
    date = ET.SubElement(dates, _q(NS_DATACITE, "date"), {"dateType": "Issued"})
    date.text = record.publication_date


def _add_resource_type(root: ET.Element, record: OpenAIRERecord) -> None:
    """11. Resource Type (M) — COAR Resource Type Vocabulary."""
    el = ET.SubElement(
        root,
        _q(NS_OAIRE, "resourceType"),
        {
            "resourceTypeGeneral": "dataset",
            "uri": record.resource_type.uri,
        },
    )
    el.text = record.resource_type.label


def _add_description(root: ET.Element, record: OpenAIRERecord) -> None:
    """12. Description (MA)."""
    if not record.description:
        return
    el = ET.SubElement(root, _q(NS_DC, "description"))
    if record.language:
        el.set(_XML_LANG, record.language)
    el.text = record.description


def _add_identifier(root: ET.Element, record: OpenAIRERecord) -> None:
    """14. Resource Identifier (M)."""
    el = ET.SubElement(root, _q(NS_DATACITE, "identifier"), {"identifierType": "URN"})
    el.text = record.identifier


def _add_access_rights(root: ET.Element, record: OpenAIRERecord) -> None:
    """15. Access Rights (M) — COAR Access Rights Vocabulary."""
    el = ET.SubElement(
        root, _q(NS_DATACITE, "rights"), {"rightsURI": record.access_rights.uri}
    )
    el.text = record.access_rights.label


def _add_subjects(root: ET.Element, record: OpenAIRERecord) -> None:
    """17. Subject (MA). Capped at 20 entries to keep records compact."""
    if not record.subjects:
        return
    subjects = ET.SubElement(root, _q(NS_DATACITE, "subjects"))
    for keyword in record.subjects[:20]:
        el = ET.SubElement(subjects, _q(NS_DATACITE, "subject"))
        el.text = keyword


def _add_temporal_coverage(root: ET.Element, record: OpenAIRERecord) -> None:
    """19. Coverage (R) — temporal."""
    if not record.temporal_coverage:
        return
    el = ET.SubElement(root, _q(NS_DC, "coverage"))
    el.text = record.temporal_coverage


def _add_spatial_coverage(root: ET.Element, record: OpenAIRERecord) -> None:
    """21. Geo Location (O) — bounding box."""
    bbox = record.spatial_coverage
    if bbox is None:
        return
    locations = ET.SubElement(root, _q(NS_DATACITE, "geoLocations"))
    location = ET.SubElement(locations, _q(NS_DATACITE, "geoLocation"))
    box = ET.SubElement(location, _q(NS_DATACITE, "geoLocationBox"))
    ET.SubElement(box, _q(NS_DATACITE, "westBoundLongitude")).text = str(bbox.west)
    ET.SubElement(box, _q(NS_DATACITE, "eastBoundLongitude")).text = str(bbox.east)
    ET.SubElement(box, _q(NS_DATACITE, "southBoundLatitude")).text = str(bbox.south)
    ET.SubElement(box, _q(NS_DATACITE, "northBoundLatitude")).text = str(bbox.north)


def _add_files(root: ET.Element, record: OpenAIRERecord) -> None:
    """23. File Location (MA)."""
    if not record.files:
        return
    for file_loc in record.files:
        attrs = {"accessRightsURI": record.access_rights.uri}
        if file_loc.mime_type:
            attrs["mimeType"] = file_loc.mime_type
        el = ET.SubElement(root, _q(NS_OAIRE, "file"), attrs)
        el.text = file_loc.url
