"""eCUDO API thin façade over `HttpClient`."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from collections.abc import AsyncIterator
from typing import TypedDict, assert_never, cast

from crawlers.core import Err, HttpClient, HttpFailure, JsonObject, Ok, Result
from crawlers.ui import console


class EcudoOrganization(TypedDict):
    """Ecudo organization dictionary."""

    id: str
    name: str
    link: str


class EcudoApiClient:
    """
    Stateless façade over `HttpClient` for the eCUDO REST API.

    Owns no session state — pass an open `HttpClient` and reuse it
    across calls. Endpoints return `Result` so the caller decides how
    to handle failures.
    """

    def __init__(self, http: HttpClient):
        self._http = http

    async def iterate_dataset_ids(
        self,
        org_id: str,
        *,
        page_size: int = 200,
        max_datasets: int | None = None,
    ) -> AsyncIterator[str]:
        """Async-iterate dataset IDs page by page, honoring `max_datasets`."""
        yielded = 0
        page = 0

        while True:
            offset = page * page_size + 1
            result = await self.list_dataset_ids(org_id, offset, page_size)

            match result:
                case Ok(value=ids) if not ids:
                    return
                case Ok(value=ids):
                    for dataset_id in ids:
                        yield dataset_id
                        yielded += 1
                        if max_datasets and yielded >= max_datasets:
                            console.info(f"Reached max_datasets limit: {max_datasets}")
                            return
                case Err(value=err):
                    console.error(str(err))
                    return
                case other:
                    assert_never(other)

            page += 1
            console.info(f"Page {page} | {yielded} IDs fetched")

    async def list_dataset_ids(
        self, org_id: str, offset: int, limit: int
    ) -> Result[list[str], HttpFailure]:
        """Fetch a page of dataset IDs for `org_id` (1-based offset)."""
        url = f"/organizations/{org_id}/data?offset={offset}&limit={limit}"
        result = await self._http.get_json_object(url)
        return result.map(_ecudo_page_metadata_ids)

    async def get_dataset_metadata(self, dataset_id: str) -> Result[JsonObject, HttpFailure]:
        """Fetch full JSON-LD metadata for one dataset."""
        return await self._http.get_json_object(f"/metadata/{dataset_id}/json-ld")

    async def get_organizations(
        self,
    ) -> Result[list[EcudoOrganization], HttpFailure]:
        """Fetch the list of available organizations."""
        result = await self._http.get_json_object("/organizations")
        return result.map(_ecudo_organizations)


def _ecudo_page_metadata_ids(d: JsonObject) -> list[str]:
    raw = d.get("metadata", [])
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw]


def _ecudo_organizations(d: JsonObject) -> list[EcudoOrganization]:
    raw = d.get("organizations", [])
    if not isinstance(raw, list):
        return []
    return cast(
        list[EcudoOrganization],
        [x for x in raw if isinstance(x, dict)],
    )
