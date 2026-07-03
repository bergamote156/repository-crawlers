"""
EODC API thin façade over `HttpClient`.

STAC API client for the EODC Earth Observation Data Centre. Owns no
session state — pass an open `HttpClient` (with `base_url` set to the
STAC API root) and reuse it across calls.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import assert_never

from crawlers.core import Err, HttpClient, HttpFailure, JsonObject, Ok, Result
from crawlers.ui import console


@dataclass(frozen=True, slots=True)
class EODCSearchParams:
    """STAC `POST /search` request parameters for `EODCClient.iterate_items`."""

    collections: list[str]
    intersects: JsonObject | None = None
    datetime_range: str | None = None
    page_size: int = 100
    max_items: int | None = None


class EODCClient:
    """
    Stateless façade over `HttpClient` for the EODC STAC API.

    Paginates `POST /search` via `rel=next` links and exposes a helper
    for listing available collections.
    """

    def __init__(self, http: HttpClient):
        self._http = http

    async def iterate_items(self, params: EODCSearchParams) -> AsyncIterator[JsonObject]:
        """
        Iterate over STAC items matching the search criteria.

        Uses `POST /search` with pagination via `rel=next` links in the
        response body.
        """
        body: JsonObject = {
            "collections": params.collections,
            "limit": params.page_size,
        }
        if params.intersects:
            body["intersects"] = params.intersects
        if params.datetime_range:
            body["datetime"] = params.datetime_range

        next_url: str | None = "/search"
        yielded = 0
        page = 0

        while next_url:
            match await self._http.post_json_object(next_url, body):
                case Ok(value=data) if not data:
                    return
                case Ok(value=data):
                    features_raw = data.get("features", [])
                    if not isinstance(features_raw, list):
                        console.debug(f"No features array in response from {next_url}")
                        return

                    features = [f for f in features_raw if isinstance(f, dict)]
                    if not features:
                        console.debug(f"No features in response from {next_url}")
                        return

                    for item in features:
                        yield item
                        yielded += 1

                        if params.max_items and yielded >= params.max_items:
                            console.info(f"Reached max_items limit: {params.max_items}")
                            return

                    page += 1
                    console.info(f"Page {page} | {yielded} items fetched")

                    next_url, body = _find_next_link(data.get("links", []))

                case Err(value=err):
                    console.error(str(err))
                    return
                case other:
                    assert_never(other)

    async def get_collections(self) -> Result[list[JsonObject], HttpFailure]:
        """Fetch the list of available STAC collections."""
        result = await self._http.get_json_object("/collections")
        return result.map(_stac_root_collections)

    async def get_collection(self, collection_id: str) -> Result[JsonObject, HttpFailure]:
        """Fetch a single STAC collection by ID."""
        return await self._http.get_json_object(f"/collections/{collection_id}")


def _stac_root_collections(root: JsonObject) -> list[JsonObject]:
    raw = root.get("collections", [])
    if not isinstance(raw, list):
        return []
    return [c for c in raw if isinstance(c, dict)]


def _find_next_link(links: object) -> tuple[str | None, JsonObject]:
    if not isinstance(links, list):
        return None, {}
    for link in links:
        if not isinstance(link, dict):
            continue
        if link.get("rel") == "next":
            href = link.get("href")
            body = link.get("body")
            return (
                str(href) if href is not None else None,
                body if isinstance(body, dict) else {},
            )
    return None, {}
