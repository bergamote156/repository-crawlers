"""
EODC STAC item parser.

Maps a STAC item dict (as returned by the EODC `POST /search` endpoint)
to an `OnedataDataset` carrying a DataCite metadata payload. This module
has no knowledge of the crawler lifecycle or HTTP — it is pure mapping,
so it can be unit-tested in isolation and the plugin file stays focused
on lifecycle wiring.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import json
import re

from crawlers.core import JsonObject
from crawlers.core.dataset import OnedataDataset, OnedataFile
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

# Default extension for assets whose MIME type we don't recognize.
_DEFAULT_ASSET_EXTENSION = "tiff"

# Generic default subjects for EODC items.
_EODC_SUBJECTS = ["Geospatial data"]

_UNSAFE_PATH_RE = re.compile(r"[^A-Za-z0-9._-]+")


def parse_eodc_item(
    raw: JsonObject,
    collection_meta: JsonObject | None = None,
) -> OnedataDataset | None:
    """
    Map a raw STAC item dict into an `OnedataDataset`.

    Returns `None` when the item should be silently skipped (missing id,
    no assets, no valid asset URLs). Unexpected errors are logged as
    warnings and also yield `None`.
    """
    item_id = raw.get("id")
    if not item_id:
        console.warning("STAC item missing 'id' field")
        return None

    try:
        return _parse_item(raw, item_id, collection_meta)
    except Exception as e:
        console.warning(f"Failed to parse STAC item {item_id}: {e}")
        return None


def parse_eodc_collection(raw: dict) -> OnedataDataset | None:
    collection_id = raw.get("id")
    if not collection_id:
        return None

    files = _parse_assets(raw.get("assets", {}))
    if not files:
        return None

    title = raw.get("title") or collection_id
    description = raw.get("description")
    if description:
        description = _sanitize_text_for_xml(description)

    dates: list[Date] = []
    temporal = raw.get("extent", {}).get("temporal", {}).get("interval", [])
    if temporal and temporal[0]:
        start, end = temporal[0]
        if start and end:
            dates.append(Date(value=f"{start}/{end}", date_type=DateType.COLLECTED))
        elif start:
            dates.append(Date(value=start, date_type=DateType.COLLECTED))

    publisher = _build_publisher(raw)
    first_date = dates[0].value.split("/")[0] if dates else None
    publication_year = year_from_iso(first_date)

    polygons: list[GeoLocationPolygon] = []
    bbox = raw.get("extent", {}).get("spatial", {}).get("bbox", [])
    if bbox and bbox[0]:
        minx, miny, maxx, maxy = bbox[0]
        polygons = [
            GeoLocationPolygon(
                points=[
                    (minx, miny),
                    (minx, maxy),
                    (maxx, maxy),
                    (maxx, miny),
                    (minx, miny),
                ]
            )
        ]

    related_identifiers = []
    self_link = _find_self_link(raw.get("links", []))
    if self_link:
        related_identifiers.append(
            RelatedIdentifier(
                value=self_link,
                identifier_type=RelatedIdentifierType.URL,
                relation_type=RelationType.IS_SUPPLEMENT_TO,
            )
        )

    metadata = DataCiteRecord(
        identifier=collection_id,
        identifier_type=IdentifierType.OTHER,
        creators=[_build_creator(raw)],
        title=title,
        publisher=publisher,
        publication_year=publication_year,
        resource_type_general="Dataset",
        resource_type_value=f"{title} dataset",
        subjects=_build_subjects({}, raw),
        dates=dates,
        geo_locations=polygons,
        descriptions=[Description(value=description or f"Collection {collection_id}")],
        related_identifiers=related_identifiers,
        rights_list=_build_rights(),
    )

    return OnedataDataset(
        name=title,
        target_dir=_build_target_dir(collection_id, title),
        pid=None,
        metadata_xml=metadata.to_xml(),
        files=tuple(files),
    )


def _parse_item(
    raw: dict,
    item_id: str,
    collection_meta: JsonObject | None = None,
) -> OnedataDataset | None:
    assets = raw.get("assets", {})
    if not assets:
        console.debug(f"Skipping {item_id}: no assets")
        return None

    files = _parse_assets(assets)
    if not files:
        console.debug(f"Skipping {item_id}: no valid asset URLs")
        return None

    props = raw.get("properties", {})
    title = _build_title(raw, props, collection_meta)
    self_link = _find_self_link(raw.get("links", []))
    dt = props.get("datetime")
    geometry = raw.get("geometry")
    collection_id = raw.get("collection")

    metadata = DataCiteRecord(
        identifier=item_id,
        identifier_type=IdentifierType.OTHER,
        creators=[_build_creator(collection_meta)],
        title=title,
        publisher=_build_publisher(collection_meta),
        publication_year=year_from_iso(dt),
        resource_type_general="Dataset",
        resource_type_value=_build_resource_type_value(collection_id),
        subjects=_build_subjects(props, collection_meta),
        descriptions=[
            _build_description(props, collection_meta, collection_id),
            Description(
                value=_build_stac_metadata_blob(raw),
                description_type="TechnicalInfo",
            ),
        ],
        rights_list=_build_rights(),
        dates=_build_dates(props),
        geo_locations=_build_geo_locations(geometry),
        related_identifiers=_build_related_identifiers(props, self_link),
    )
    return OnedataDataset(
        name=title,
        target_dir=_build_target_dir(item_id, title),
        pid=None,
        metadata_xml=metadata.to_xml(),
        files=tuple(files),
    )


def _build_title(raw: dict, props: dict, collection_meta: JsonObject | None) -> str:
    """
    Build a generic title for an EODC STAC item.

    Prefer the STAC item's own `title`. Otherwise, use collection title
    or collection id, optionally appending datetime in parentheses.
    """

    if raw.get("title"):
        return str(raw["title"])

    collection_label = None
    if collection_meta and collection_meta.get("title"):
        collection_label = collection_meta["title"]
    elif raw.get("collection"):
        collection_label = raw["collection"]
    else:
        collection_label = raw.get("id", "EODC dataset")

    dt = props.get("datetime")
    if dt:
        return f"{collection_label} ({dt})"

    return str(collection_label)


def _parse_assets(assets: dict) -> list[OnedataFile]:
    """Parse a STAC 'assets' dict into a list of `OnedataFile`."""
    files: list[OnedataFile] = []
    for name, asset in assets.items():
        href = asset.get("href")
        if not href:
            continue

        roles = asset.get("roles", [])
        if isinstance(roles, list) and "thumbnail" in roles:
            continue

        if "tilejson.json" in href or "titiler" in href:
            continue

        if ".zarr/" in href or href.endswith(".zarr"):
            files.append(OnedataFile(path=name + ".zarr.json", url=href.rstrip("/") + "/zarr.json"))
            continue

        ext = extension_for_mime(asset.get("type")) or _DEFAULT_ASSET_EXTENSION
        files.append(OnedataFile(path=f"{name}.{ext}", url=href))

    return files


def _find_self_link(links: list) -> str | None:
    """Find the 'rel=self' link in STAC item links."""
    for link in links:
        if link.get("rel") == "self":
            href: str | None = link.get("href")
            return href
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


def _build_geo_locations(geometry: dict | None) -> list[GeoLocationPolygon]:
    """Convert GeoJSON geometry to DataCite geo locations."""
    return _polygons_from_geojson(geometry)


def _build_dates(props: dict) -> list[Date]:

    dates: list[Date] = []
    seen: set[tuple[str, str]] = set()

    def add_date(value: str | None, dtype: DateType) -> None:
        if not value:
            return
        key = (value, dtype.value)
        if key not in seen:
            dates.append(Date(value=value, date_type=dtype))
            seen.add(key)

    dt = props.get("datetime")
    start = props.get("start_datetime")
    end = props.get("end_datetime")

    if start and end:
        interval = f"{start}/{end}"
        add_date(interval, DateType.COLLECTED)

        if start != end:
            add_date(start, DateType.COLLECTED)
            add_date(end, DateType.COLLECTED)

    elif dt:
        add_date(dt, DateType.COLLECTED)

    elif start:
        add_date(start, DateType.COLLECTED)

    elif end:
        add_date(end, DateType.COLLECTED)

    add_date(props.get("created"), DateType.CREATED)

    add_date(props.get("updated"), DateType.UPDATED)

    add_date(props.get("processing:datetime"), DateType.ISSUED)

    return dates


def _build_related_identifiers(props: dict, self_link: str | None) -> list[RelatedIdentifier]:

    related = []

    if self_link:
        related.append(
            RelatedIdentifier(
                value=self_link,
                identifier_type=RelatedIdentifierType.URL,
                relation_type=RelationType.IS_SUPPLEMENT_TO,
            )
        )

    if props.get("sci:doi"):
        related.append(
            RelatedIdentifier(
                value=props["sci:doi"],
                identifier_type=RelatedIdentifierType.DOI,
                relation_type=RelationType.IS_REFERENCED_BY,
            )
        )

    return related


def _build_creator(collection_meta: dict | None) -> Creator:
    if collection_meta:
        providers = collection_meta.get("providers", [])
        for p in providers:
            if "producer" in p.get("roles", []) or "processor" in p.get("roles", []):
                return Creator(
                    name=p.get("name", "Unknown"),
                    name_type=NameType.ORGANIZATIONAL,
                )

    # fallback
    return Creator(
        name="Unknown provider",
        name_type=NameType.ORGANIZATIONAL,
    )


def _build_publisher(collection_meta: dict | None) -> str:
    if collection_meta:
        providers = collection_meta.get("providers", [])
        for p in providers:
            if "host" in p.get("roles", []):
                name: str = p.get("name")
                return name

    return "EODC"


def _build_resource_type_value(collection_id: str | None) -> str:
    if collection_id:
        return f"{collection_id} dataset"
    return "Earth observation data"


def _build_subjects(props: dict, collection_meta: JsonObject | None) -> list[str]:

    subjects = set(_EODC_SUBJECTS)

    if collection_meta and collection_meta.get("keywords"):
        subjects.update(str(k) for k in collection_meta["keywords"])

    if props.get("eo:common_name"):
        subjects.add(str(props["eo:common_name"]))

    if props.get("product:type"):
        subjects.add(str(props["product:type"]))

    if props.get("platform"):
        subjects.add(str(props["platform"]))

    subjects.add("Earth Observation")

    return sorted(subjects)


def _build_stac_metadata_blob(raw: dict) -> str:
    """Build a JSON blob of full STAC properties metadata."""
    props = raw.get("properties", {})
    return json.dumps(props, separators=(",", ":")) if props else "{}"


def _sanitize_text_for_xml(text: str) -> str:
    if not text:
        return text
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _build_description(
    props: dict,
    collection_meta: JsonObject | None,
    collection_id: str | None,
) -> Description:
    if collection_meta and collection_meta.get("description"):
        return Description(value=_sanitize_text_for_xml(collection_meta["description"]))

    if collection_id:
        return Description(value=f"Dataset from STAC collection: {collection_id}")

    return Description(value="Earth observation dataset")


def _build_rights() -> list[Rights]:
    return [Rights(text="Usage subject to EODC data policy")]


def _build_target_dir(item_id: str, title: str) -> str:
    """Build a filesystem-safe directory name, preferring the item identifier."""
    candidate = item_id or title or "eodc-dataset"
    sanitized = _UNSAFE_PATH_RE.sub("-", candidate).strip("-_. ")
    return sanitized or "eodc-dataset"
