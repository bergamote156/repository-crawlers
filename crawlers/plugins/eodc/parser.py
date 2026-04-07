"""
EODC Parser.

Parses STAC items from EODC API into EODCDataset models.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Sequence

from crawlers.metadata.datacite import (
    Creator,
    DataCiteRecord,
    Date,
    DateType,
    Description,
    GeoLocationPolygon,
    IdentifierType,
    NameType,
    RelatedIdentifier,
    RelatedIdentifierType,
    RelationType,
    Rights,
)
from crawlers.processors.parsers import Parser
from crawlers.ui import console

# --- EODC Sentinel-1 GRD constants -------------------------------------------
# These defaults describe Copernicus Sentinel-1 GRD products. Move them to
# config if EODC ever serves additional collections.

_EODC_CREATOR = Creator(name="European Space Agency", name_type=NameType.ORGANIZATIONAL)
_EODC_PUBLISHER = "EODC"
_EODC_RESOURCE_TYPE_VALUE = "Earth observation data"
_EODC_SUBJECTS = [
    "Sentinel-1",
    "Synthetic Aperture Radar",
    "SAR",
    "GRD",
    "Copernicus",
]
_EODC_DESCRIPTION = Description(
    value=(
        "Sentinel-1 Level-1 Ground Range Detected (GRD) product "
        "acquired in Interferometric Wide (IW) mode. "
        "Data provided as part of the Copernicus Earth Observation programme."
    ),
)
_EODC_RIGHTS = Rights(text="Copernicus Open Access Licence")

# MIME type to file extension mapping
MIME_EXTENSIONS = {
    "application/zip": "zip",
    "image/png": "png",
    "image/tiff": "tiff",
    "application/xml": "xml",
    "application/json": "json",
    "text/plain": "txt",
}

# Default extension for unknown MIME types
DEFAULT_EXTENSION = "tiff"


@dataclass
class EODCFile:
    """Asset from STAC item."""

    path: str
    url: str


@dataclass
class EODCDataset:
    """Pipeline carrier for an EODC STAC item with prebuilt DataCite record."""

    identifier: str
    title: str
    files: Sequence[EODCFile]
    metadata_record: DataCiteRecord
    _raw: dict = field(default_factory=dict, repr=False, compare=False)

    def to_json(self) -> dict:
        """Return the raw STAC item data."""
        return self._raw


# pylint: disable=too-few-public-methods
class EODCParser(Parser[dict, EODCDataset]):
    """
    Parses STAC Item dict to EODCDataset.

    Handles:
    - Dynamic title generation from Sentinel-1 properties
    - Asset extraction with MIME type inference
    - GeoJSON geometry extraction
    """

    def parse(self, raw: dict) -> EODCDataset | None:
        """
        Parse raw STAC item data.

        Args:
            raw: Dictionary with STAC item data

        Returns:
            EODCDataset or None if parsing fails or data is invalid
        """
        item_id = raw.get("id")
        if not item_id:
            console.warning("STAC item missing 'id' field")
            return None

        try:
            return self._parse_item(raw, item_id)
        except Exception as e:  # pylint: disable=broad-except
            console.warning(f"Failed to parse STAC item {item_id}: {e}")
            return None

    def _parse_item(self, raw: dict, item_id: str) -> EODCDataset | None:
        """Internal parsing logic."""
        props = raw.get("properties", {})

        # Extract assets
        assets = raw.get("assets", {})
        if not assets:
            console.debug(f"Skipping {item_id}: no assets")
            return None

        files = self._parse_assets(assets)
        if not files:
            console.debug(f"Skipping {item_id}: no valid asset URLs")
            return None

        # Build dynamic title
        title = self._build_title(props)

        # Find self link
        self_link = self._find_self_link(raw.get("links", []))

        dt = props.get("datetime")
        geometry = raw.get("geometry")

        record = DataCiteRecord(
            identifier=item_id,
            identifier_type=IdentifierType.OTHER,
            creators=[_EODC_CREATOR],
            title=title,
            publisher=_EODC_PUBLISHER,
            publication_year=_year_from_datetime(dt),
            resource_type_general="Dataset",
            resource_type_value=_EODC_RESOURCE_TYPE_VALUE,
            subjects=list(_EODC_SUBJECTS),
            dates=([Date(value=dt, date_type=DateType.COLLECTED)] if dt else []),
            geo_locations=_polygons_from_geojson(geometry),
            descriptions=[_EODC_DESCRIPTION],
            related_identifiers=(
                [
                    RelatedIdentifier(
                        value=self_link,
                        identifier_type=RelatedIdentifierType.URL,
                        relation_type=RelationType.IS_SUPPLEMENT_TO,
                    )
                ]
                if self_link
                else []
            ),
            rights_list=[_EODC_RIGHTS],
        )

        return EODCDataset(
            identifier=item_id,
            title=title,
            files=files,
            metadata_record=record,
            _raw=raw,
        )

    def _build_title(self, props: dict) -> str:
        """
        Build dynamic title from Sentinel-1 properties.

        Format: "{PLATFORM} {MODE} GRD ({POLARIZATIONS}) sensing {DATETIME} rel. orbit {ORBIT}"

        Args:
            props: Properties dict from STAC item

        Returns:
            Generated title string
        """
        platform = props.get("platform", "Sentinel-1").upper()
        mode = props.get("sar:instrument_mode", "IW")
        polarizations = ",".join(props.get("sar:polarizations", []))
        dt = props.get("datetime", "")
        orbit = props.get("sat:relative_orbit")

        title_parts = [
            platform,
            f"{mode} GRD",
        ]

        if polarizations:
            title_parts.append(f"({polarizations})")

        if dt:
            title_parts.append(f"sensing {dt}")

        if orbit is not None:
            title_parts.append(f"rel. orbit {orbit}")

        return " ".join(title_parts)

    def _parse_assets(self, assets: dict) -> list[EODCFile]:
        """
        Parse assets dict into list of EODCFile.

        Args:
            assets: Assets dict from STAC item {name: {href, type, ...}}

        Returns:
            List of EODCFile objects
        """
        files = []

        for name, asset in assets.items():
            href = asset.get("href")
            if not href:
                continue

            mime_type = asset.get("type")
            ext = self._get_extension(mime_type)
            filename = f"{name}.{ext}"

            files.append(
                EODCFile(
                    path=filename,
                    url=href,
                )
            )

        return files

    def _get_extension(self, mime_type: str | None) -> str:
        """
        Get file extension from MIME type.

        Args:
            mime_type: MIME type string or None

        Returns:
            File extension without dot
        """
        if not mime_type:
            return DEFAULT_EXTENSION

        mime_lower = mime_type.lower()

        # Check direct mapping
        for mime, ext in MIME_EXTENSIONS.items():
            if mime in mime_lower:
                return ext

        return DEFAULT_EXTENSION

    def _find_self_link(self, links: list) -> str | None:
        """Find the self link in STAC item links."""
        for link in links:
            if link.get("rel") == "self":
                return link.get("href")
        return None


def _year_from_datetime(dt: str | None) -> int:
    """Extract publication year from an ISO 8601 string, fall back to UTC now."""
    if dt:
        try:
            return int(dt[:4])
        except (ValueError, IndexError):
            pass
    return datetime.now(UTC).year


def _polygons_from_geojson(geom: dict | None) -> list[GeoLocationPolygon]:
    """Convert a GeoJSON Polygon geometry into DataCite polygons."""
    if not geom or geom.get("type") != "Polygon":
        return []
    coords = geom.get("coordinates", [])
    if not coords or not coords[0]:
        return []
    # GeoJSON Polygon: list of linear rings, first is outer ring; each point
    # is [lon, lat]. We only emit the outer ring.
    return [GeoLocationPolygon(points=[(lon, lat) for lon, lat in coords[0]])]
