"""
EODC STAC item parser.

Maps a STAC item dict (as returned by the EODC `POST /search` endpoint)
to a `DataCiteRecord` plus the list of downloadable assets. This module
has no knowledge of the crawler lifecycle or HTTP — it is pure mapping,
so it can be unit-tested in isolation and the plugin file stays focused
on lifecycle wiring.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass

from crawlers.core import JsonObject
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
from crawlers.plugins.utils.datetime import year_from_iso
from crawlers.plugins.utils.mime import extension_for_mime
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

# Default extension for assets whose MIME type we don't recognize.
_DEFAULT_ASSET_EXTENSION = "tiff"


@dataclass
class EODCFile:
    """A single downloadable asset from a STAC item."""

    path: str
    url: str


@dataclass
class ParsedEODCItem:
    """Result of parsing a single EODC STAC item."""

    identifier: str
    title: str
    metadata: DataCiteRecord
    files: list[EODCFile]


def parse_eodc_item(raw: JsonObject) -> ParsedEODCItem | None:
    """
    Map a raw STAC item dict into a `ParsedEODCItem`.

    Returns `None` when the item should be silently skipped (missing id,
    no assets, no valid asset URLs). Unexpected errors are logged as
    warnings and also yield `None`.
    """
    item_id = raw.get("id")
    if not item_id:
        console.warning("STAC item missing 'id' field")
        return None

    try:
        return _parse_item(raw, item_id)
    except Exception as e:  # pylint: disable=broad-except
        console.warning(f"Failed to parse STAC item {item_id}: {e}")
        return None


def _parse_item(raw: dict, item_id: str) -> ParsedEODCItem | None:
    assets = raw.get("assets", {})
    if not assets:
        console.debug(f"Skipping {item_id}: no assets")
        return None

    files = _parse_assets(assets)
    if not files:
        console.debug(f"Skipping {item_id}: no valid asset URLs")
        return None

    props = raw.get("properties", {})
    title = _build_title(props)
    self_link = _find_self_link(raw.get("links", []))
    dt = props.get("datetime")
    geometry = raw.get("geometry")

    metadata = DataCiteRecord(
        identifier=item_id,
        identifier_type=IdentifierType.OTHER,
        creators=[_EODC_CREATOR],
        title=title,
        publisher=_EODC_PUBLISHER,
        publication_year=year_from_iso(dt),
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

    return ParsedEODCItem(
        identifier=item_id,
        title=title,
        metadata=metadata,
        files=files,
    )


def _build_title(props: dict) -> str:
    """
    Build dynamic title from Sentinel-1 properties.

    Format: "{PLATFORM} {MODE} GRD ({POLARIZATIONS}) sensing {DATETIME} rel. orbit {ORBIT}"
    """
    platform = props.get("platform", "Sentinel-1").upper()
    mode = props.get("sar:instrument_mode", "IW")
    polarizations = ",".join(props.get("sar:polarizations", []))
    dt = props.get("datetime", "")
    orbit = props.get("sat:relative_orbit")

    title_parts = [platform, f"{mode} GRD"]

    if polarizations:
        title_parts.append(f"({polarizations})")

    if dt:
        title_parts.append(f"sensing {dt}")

    if orbit is not None:
        title_parts.append(f"rel. orbit {orbit}")

    return " ".join(title_parts)


def _parse_assets(assets: dict) -> list[EODCFile]:
    """Parse a STAC 'assets' dict into a list of `EODCFile`."""
    files: list[EODCFile] = []
    for name, asset in assets.items():
        href = asset.get("href")
        if not href:
            continue

        ext = extension_for_mime(asset.get("type")) or _DEFAULT_ASSET_EXTENSION
        files.append(EODCFile(path=f"{name}.{ext}", url=href))

    return files


def _find_self_link(links: list) -> str | None:
    """Find the 'rel=self' link in STAC item links."""
    for link in links:
        if link.get("rel") == "self":
            return link.get("href")
    return None


def _polygons_from_geojson(geom: dict | None) -> list[GeoLocationPolygon]:
    """Convert a GeoJSON Polygon geometry into DataCite polygons."""
    if not geom or geom.get("type") != "Polygon":
        return []
    coords = geom.get("coordinates", [])
    if not coords or not coords[0]:
        return []
    # GeoJSON Polygon: list of linear rings, first is outer ring; each point
    # is [lon, lat]. We only emit the outer ring.
    return [GeoLocationPolygon(points=[tuple(point) for point in coords[0]])]
