"""
EODC API Client.

STAC API client for EODC Earth Observation Data Centre.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass
from typing import AsyncIterator

from crawlers.core.abc.api import ApiClient
from crawlers.core.ui import console


@dataclass
class EODCSearchOpts:
    """Options for STAC search."""

    collections: list[str]
    intersects: dict | None = None  # GeoJSON geometry for spatial filter
    datetime: str | None = None  # ISO datetime range "2025-01-01/2025-01-31"
    limit: int = 100
    max_items: int | None = None


class EODCClient(ApiClient[EODCSearchOpts, dict]):
    """
    STAC API Client for EODC.

    Iterates over STAC items (dict) using POST /search endpoint.
    Handles pagination via 'next' links.
    """

    # pylint: disable=invalid-overridden-method
    async def iterate_datasets(self, opts: EODCSearchOpts) -> AsyncIterator[dict]:
        """
        Iterate over STAC items matching search criteria.

        Uses POST /search with pagination via 'next' links.

        Args:
            opts: Search options including collections and filters

        Yields:
            STAC item dict (raw)
        """
        url: str | None = f"{self.base_url}/search"
        body = self._build_search_body(opts)

        yielded = 0
        page = 0

        while url:
            data = await self.post_json(url, body)

            if not data:
                console.warning(f"Empty response from STAC API at {url}")
                break

            features = data.get("features", [])
            if not features:
                console.debug(f"No features in response from {url}")
                break

            for item in features:
                yield item
                yielded += 1

                if opts.max_items and yielded >= opts.max_items:
                    console.info(f"Reached max_items limit: {opts.max_items}")
                    return

            page += 1
            console.info(f"📄 Page {page} | {yielded} items fetched")

            # Find next page link
            url = self._find_next_link(data.get("links", []))

            # For subsequent pages, we use the URL directly (it contains state)
            # Some STAC APIs use body for pagination, others use URL params
            # EODC seems to use URL-based pagination

        console.info(f"STAC iteration complete. Total: {yielded}")

    def _build_search_body(self, opts: EODCSearchOpts) -> dict:
        """
        Build STAC search request body.

        Args:
            opts: Search options

        Returns:
            Request body dict
        """
        body: dict = {
            "collections": opts.collections,
            "limit": opts.limit,
        }

        if opts.intersects:
            body["intersects"] = opts.intersects

        if opts.datetime:
            body["datetime"] = opts.datetime

        return body

    def _find_next_link(self, links: list) -> str | None:
        """
        Find the 'next' pagination link.

        Args:
            links: List of link dicts from STAC response

        Returns:
            URL of next page or None
        """
        for link in links:
            if link.get("rel") == "next":
                return link.get("href")
        return None

    async def get_collections(self) -> list[dict]:
        """
        Fetch list of available STAC collections.

        Returns:
            List of collection dicts
        """
        data = await self.get_json(f"{self.base_url}/collections")
        return data.get("collections", [])
