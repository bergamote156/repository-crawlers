"""
EODC API thin façade over `HttpClient`.

STAC API client for the EODC Earth Observation Data Centre. Owns no
session state — pass an open `HttpClient` (with `base_url` set to the
STAC API root) and reuse it across calls.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from typing import AsyncIterator, assert_never

from crawlers.core import Err, HttpClient, HttpFailure, Ok, Result
from crawlers.ui import console


class EODCClient:
    """
    Stateless façade over `HttpClient` for the EODC STAC API.

    Paginates `POST /search` via `rel=next` links and exposes a helper
    for listing available collections.
    """

    def __init__(self, http: HttpClient):
        self._http = http

    async def iterate_items(
        self,
        collections: list[str],
        *,
        intersects: dict | None = None,
        datetime: str | None = None,  # pylint: disable=redefined-outer-name
        page_size: int = 100,
        max_items: int | None = None,
    ) -> AsyncIterator[dict]:
        """
        Iterate over STAC items matching the search criteria.

        Uses `POST /search` with pagination via `rel=next` links in the
        response body.
        """
        body: dict = {"collections": collections, "limit": page_size}
        if intersects:
            body["intersects"] = intersects
        if datetime:
            body["datetime"] = datetime

        next_url: str | None = "/search"
        yielded = 0
        page = 0

        while next_url:
            match await self._http.post_json(next_url, body):
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

                        if max_items and yielded >= max_items:
                            console.info(f"Reached max_items limit: {max_items}")
                            return

                    page += 1
                    console.info(f"Page {page} | {yielded} items fetched")

                    next_url = _find_next_link(data.get("links", []))

                case Err(value=err):
                    console.error(str(err))
                    return
                case other:
                    assert_never(other)

    async def get_collections(self) -> Result[list[dict], HttpFailure]:
        """Fetch the list of available STAC collections."""
        result = await self._http.get_json("/collections")
        return result.map(lambda d: d.get("collections", []))


def _find_next_link(links: list) -> str | None:
    for link in links:
        if link.get("rel") == "next":
            return link.get("href")
    return None
