"""
EODC Parser.

Parses STAC items from EODC API into EODCDataset models.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from crawlers.core.ui import console
from crawlers.core.processors.fetchers import Parser
from crawlers.plugins.eodc.models import EODCDataset, EODCFile

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

        return EODCDataset(
            identifier=item_id,
            title=title,
            files=files,
            geometry=raw.get("geometry"),
            datetime=props.get("datetime"),
            self_link=self_link,
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
                    name=filename,
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
        """
        Find self link in STAC item links.

        Args:
            links: List of link dicts from STAC item

        Returns:
            URL of self link or None
        """
        for link in links:
            if link.get("rel") == "self":
                return link.get("href")
        return None
