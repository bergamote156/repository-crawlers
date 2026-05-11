"""
DataCite Metadata Builder.

Generates DataCite Kernel 4.5 compliant XML metadata.
https://schema.datacite.org/meta/kernel-4.5/

The builder consumes a structured `DataCiteRecord` describing a single
resource. Plugins are responsible for converting their domain dataset into a
record — the builder stays ignorant of source-specific defaults, fallbacks
and ad-hoc parsing.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum

# ─────────────────────────────────────────────────────────────────────────────
# Namespaces
# ─────────────────────────────────────────────────────────────────────────────

NS_DATACITE = "http://datacite.org/schema/kernel-4"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"

_SCHEMA_LOCATION = (
    "http://datacite.org/schema/kernel-4 http://schema.datacite.org/meta/kernel-4.5/metadata.xsd"
)


def _q(ns: str, tag: str) -> str:
    """Build an ElementTree Clark-notation tag."""
    return f"{{{ns}}}{tag}"


# ─────────────────────────────────────────────────────────────────────────────
# Vocabularies
# ─────────────────────────────────────────────────────────────────────────────


class IdentifierType(Enum):
    """DataCite identifier types (subset)."""

    DOI = "DOI"
    URL = "URL"
    URN = "URN"
    OTHER = "Other"


class DateType(Enum):
    """DataCite date types (subset)."""

    COLLECTED = "Collected"
    UPDATED = "Updated"
    ISSUED = "Issued"
    CREATED = "Created"
    SUBMITTED = "Submitted"


class RelatedIdentifierType(Enum):
    """DataCite related-identifier types (subset)."""

    DOI = "DOI"
    URL = "URL"


class RelationType(Enum):
    """DataCite relation types (subset)."""

    IS_SUPPLEMENT_TO = "IsSupplementTo"
    IS_REFERENCED_BY = "IsReferencedBy"


class NameType(Enum):
    """DataCite creator name types."""

    PERSONAL = "Personal"
    ORGANIZATIONAL = "Organizational"


# ─────────────────────────────────────────────────────────────────────────────
# Record model
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class NameIdentifier:
    """An external identifier attached to a creator (ORCID, ROR, URL, ...)."""

    value: str
    scheme: str  # e.g. "URL", "ORCID", "ROR"


@dataclass
class Creator:
    """A DataCite 'creator' element."""

    name: str
    name_type: NameType = NameType.ORGANIZATIONAL
    identifiers: list[NameIdentifier] = field(default_factory=list)


@dataclass
class Date:
    """A DataCite 'date' element."""

    value: str
    date_type: DateType


@dataclass
class GeoLocationPolygon:
    """A DataCite 'geoLocationPolygon' — list of (longitude, latitude) points."""

    points: list[tuple[float, float]]


@dataclass
class RelatedIdentifier:
    """A DataCite 'relatedIdentifier' element."""

    value: str
    identifier_type: RelatedIdentifierType
    relation_type: RelationType


@dataclass
class Description:
    """A DataCite 'description' element."""

    value: str
    description_type: str = "Abstract"


@dataclass
class Rights:
    """A DataCite 'rights' element with optional URI."""

    text: str
    uri: str | None = None


@dataclass
class DataCiteRecord:
    """
    Structured record for building DataCite XML.

    Mandatory properties (M in DataCite Kernel 4.5) have no default — the
    dataclass constructor enforces their presence. Recommended/Optional fields
    default to 'None' / empty collections; sections corresponding to absent
    fields are not emitted.
    """

    # Mandatory
    identifier: str
    identifier_type: IdentifierType
    creators: list[Creator]
    title: str
    publisher: str
    publication_year: int
    resource_type_general: str  # e.g. "Dataset", "Image", "Software"
    resource_type_value: str  # free-form sub-type label

    # Recommended / Optional
    subjects: list[str] = field(default_factory=list)
    dates: list[Date] = field(default_factory=list)
    geo_locations: list[GeoLocationPolygon] = field(default_factory=list)
    descriptions: list[Description] = field(default_factory=list)
    related_identifiers: list[RelatedIdentifier] = field(default_factory=list)
    rights_list: list[Rights] = field(default_factory=list)
    version: str | None = None

    def to_xml(self) -> str:
        """Build DataCite XML."""
        return _build(self)


# ─────────────────────────────────────────────────────────────────────────────
# Builder
# ─────────────────────────────────────────────────────────────────────────────


def _build(record: DataCiteRecord) -> str:
    root = ET.Element(
        _q(NS_DATACITE, "resource"),
        {_q(NS_XSI, "schemaLocation"): _SCHEMA_LOCATION},
    )

    _add_identifier(root, record)
    _add_creators(root, record)
    _add_titles(root, record)
    _add_publisher(root, record)
    _add_publication_year(root, record)
    _add_resource_type(root, record)
    _add_subjects(root, record)
    _add_dates(root, record)
    _add_geo_locations(root, record)
    _add_descriptions(root, record)
    _add_related_identifiers(root, record)
    _add_rights_list(root, record)
    _add_version(root, record)

    # Configure namespace serialization locally rather than globally for ET,
    # as it impacts all other places where ET is used (other metadata model implementations).
    ET.register_namespace("", NS_DATACITE)
    ET.register_namespace("xsi", NS_XSI)

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True, short_empty_elements=False)


# ─────────────────────────────────────────────────────────────────────────────
# Section builders (private)
# ─────────────────────────────────────────────────────────────────────────────


def _add_identifier(root: ET.Element, record: DataCiteRecord) -> None:
    el = ET.SubElement(
        root,
        _q(NS_DATACITE, "identifier"),
        {"identifierType": record.identifier_type.value},
    )
    el.text = record.identifier


def _add_creators(root: ET.Element, record: DataCiteRecord) -> None:
    creators = ET.SubElement(root, _q(NS_DATACITE, "creators"))
    for creator in record.creators:
        creator_el = ET.SubElement(creators, _q(NS_DATACITE, "creator"))
        ET.SubElement(
            creator_el,
            _q(NS_DATACITE, "creatorName"),
            {"nameType": creator.name_type.value},
        ).text = creator.name
        for ident in creator.identifiers:
            ET.SubElement(
                creator_el,
                _q(NS_DATACITE, "nameIdentifier"),
                {"nameIdentifierScheme": ident.scheme},
            ).text = ident.value


def _add_titles(root: ET.Element, record: DataCiteRecord) -> None:
    titles = ET.SubElement(root, _q(NS_DATACITE, "titles"))
    ET.SubElement(titles, _q(NS_DATACITE, "title")).text = record.title


def _add_publisher(root: ET.Element, record: DataCiteRecord) -> None:
    ET.SubElement(root, _q(NS_DATACITE, "publisher")).text = record.publisher


def _add_publication_year(root: ET.Element, record: DataCiteRecord) -> None:
    ET.SubElement(root, _q(NS_DATACITE, "publicationYear")).text = str(record.publication_year)


def _add_resource_type(root: ET.Element, record: DataCiteRecord) -> None:
    el = ET.SubElement(
        root,
        _q(NS_DATACITE, "resourceType"),
        {"resourceTypeGeneral": record.resource_type_general},
    )
    el.text = record.resource_type_value


def _add_subjects(root: ET.Element, record: DataCiteRecord) -> None:
    if not record.subjects:
        return
    subjects = ET.SubElement(root, _q(NS_DATACITE, "subjects"))
    for kw in record.subjects:
        ET.SubElement(subjects, _q(NS_DATACITE, "subject")).text = kw


def _add_dates(root: ET.Element, record: DataCiteRecord) -> None:
    if not record.dates:
        return
    dates = ET.SubElement(root, _q(NS_DATACITE, "dates"))
    for date in record.dates:
        ET.SubElement(
            dates, _q(NS_DATACITE, "date"), {"dateType": date.date_type.value}
        ).text = date.value


def _add_geo_locations(root: ET.Element, record: DataCiteRecord) -> None:
    if not record.geo_locations:
        return
    geo_locs = ET.SubElement(root, _q(NS_DATACITE, "geoLocations"))
    for loc in record.geo_locations:
        if not loc.points:
            continue
        geo_loc = ET.SubElement(geo_locs, _q(NS_DATACITE, "geoLocation"))
        polygon = ET.SubElement(geo_loc, _q(NS_DATACITE, "geoLocationPolygon"))
        for lon, lat in loc.points:
            point = ET.SubElement(polygon, _q(NS_DATACITE, "polygonPoint"))
            ET.SubElement(point, _q(NS_DATACITE, "pointLongitude")).text = str(lon)
            ET.SubElement(point, _q(NS_DATACITE, "pointLatitude")).text = str(lat)


def _add_descriptions(root: ET.Element, record: DataCiteRecord) -> None:
    if not record.descriptions:
        return
    descriptions = ET.SubElement(root, _q(NS_DATACITE, "descriptions"))
    for desc in record.descriptions:
        ET.SubElement(
            descriptions,
            _q(NS_DATACITE, "description"),
            {"descriptionType": desc.description_type},
        ).text = desc.value


def _add_related_identifiers(root: ET.Element, record: DataCiteRecord) -> None:
    if not record.related_identifiers:
        return
    related = ET.SubElement(root, _q(NS_DATACITE, "relatedIdentifiers"))
    for rel in record.related_identifiers:
        ET.SubElement(
            related,
            _q(NS_DATACITE, "relatedIdentifier"),
            {
                "relatedIdentifierType": rel.identifier_type.value,
                "relationType": rel.relation_type.value,
            },
        ).text = rel.value


def _add_rights_list(root: ET.Element, record: DataCiteRecord) -> None:
    if not record.rights_list:
        return
    rights_list = ET.SubElement(root, _q(NS_DATACITE, "rightsList"))
    for r in record.rights_list:
        attrs = {"rightsURI": r.uri} if r.uri else {}
        ET.SubElement(rights_list, _q(NS_DATACITE, "rights"), attrs).text = r.text


def _add_version(root: ET.Element, record: DataCiteRecord) -> None:
    if record.version is None:
        return
    ET.SubElement(root, _q(NS_DATACITE, "version")).text = record.version
