"""
EODC API Client.

STAC API client for EODC Earth Observation Data Centre.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass
from typing import AsyncIterator, assert_never

from crawlers.core.api import ApiClient, ApiFailure
from crawlers.core.result import Err, Ok, Result
from crawlers.ui import console


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
        next_url: str | None = f"{self.base_url}/search"
        body = _build_search_body(opts)
        yielded = 0
        page = 0

        while next_url:
            match await self.post_json(next_url, body):
                case Ok(value=data) if not data:
                    return
                case Ok(value=data):
                    features = data.get("features", [])
                    if not features:
                        console.debug(f"No features in response from {next_url}")
                        return

                    for item in features:
                        yield item
                        yielded += 1

                        if opts.max_items and yielded >= opts.max_items:
                            console.info(f"Reached max_items limit: {opts.max_items}")
                            return

                    page += 1
                    console.info(f"📄 Page {page} | {yielded} items fetched")

                    # Find next page link
                    next_url = _find_next_link(data.get("links", []))

                case Err(value=err):
                    console.error(str(err))
                    return
                case other:
                    assert_never(other)

    async def get_collections(self) -> Result[list[dict], ApiFailure]:
        """
        Fetch list of available STAC collections.

        Returns:
            Ok(list[dict]) of collections, or Err(ApiFailure)
        """
        result = await self.get_json(f"{self.base_url}/collections")
        return result.map(lambda d: d.get("collections", []))


def _build_search_body(opts: EODCSearchOpts) -> dict:
    body: dict = {"collections": opts.collections, "limit": opts.limit}
    if opts.intersects:
        body["intersects"] = opts.intersects
    if opts.datetime:
        body["datetime"] = opts.datetime
    return body


def _find_next_link(links: list) -> str | None:
    for link in links:
        if link.get("rel") == "next":
            return link.get("href")
    return None
