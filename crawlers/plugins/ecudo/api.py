"""
Ecudo API Client.
"""

# pylint: disable=duplicate-code

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass
from typing import AsyncIterator, Self, TypedDict, assert_never

from crawlers.core.api import ApiClient, ApiFailure
from crawlers.core.result import Err, Ok, Result
from crawlers.plugins.ecudo.config import EcudoApiConfig
from crawlers.ui import console


@dataclass
class EcudoIteratorOpts:
    """Options for iterating over Ecudo datasets."""

    org_id: str
    page_size: int = 200
    max_datasets: int | None = None


class EcudoOrganization(TypedDict):
    """Ecudo organization dictionary."""

    id: str
    name: str
    link: str


class EcudoClient(ApiClient[EcudoIteratorOpts, str]):
    """
    API Client for Ecudo.

    Iterates over dataset IDs (str).
    Provides method to fetch full metadata for a given ID.
    """

    @classmethod
    def from_config(cls, config: EcudoApiConfig) -> Self:
        """Construct client object."""
        return cls(
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    # pylint: disable=invalid-overridden-method
    async def iterate_datasets(self, opts: EcudoIteratorOpts) -> AsyncIterator[str]:
        """
        Iterate over dataset IDs in the specified organization.

        Args:
            opts: Iteration options including org_id and limits

        Yields:
            Dataset ID (str)
        """
        yielded = 0
        page = 0

        while True:
            offset = page * opts.page_size + 1
            result = await self.list_dataset_ids(opts.org_id, offset, opts.page_size)

            match result:
                case Ok(value=ids) if not ids:
                    return
                case Ok(value=ids):
                    for dataset_id in ids:
                        yield dataset_id
                        yielded += 1

                        if opts.max_datasets and yielded >= opts.max_datasets:
                            console.info(
                                f"Reached max_datasets limit: {opts.max_datasets}"
                            )
                            return
                case Err(value=err):
                    console.error(str(err))
                    return
                case other:
                    assert_never(other)

            page += 1
            console.info(f"📄 Page {page} | {yielded} IDs fetched")

    async def list_dataset_ids(
        self, org_id: str, offset: int, limit: int
    ) -> Result[list[str], ApiFailure]:
        """
        Fetch a page of dataset IDs.

        Args:
            org_id: Organization ID
            offset: Pagination offset (1-based)
            limit: Number of items per page

        Returns:
            Ok(list[str]) of dataset IDs, or Err(ApiFailure)
        """
        url = (
            f"{self.base_url}/organizations/{org_id}/data?offset={offset}&limit={limit}"
        )
        return (await self.get_json(url)).map(lambda d: d.get("metadata", []))

    async def get_dataset_metadata(self, dataset_id: str) -> Result[dict, ApiFailure]:
        """
        Fetch full JSON-LD metadata for a dataset.

        Args:
            dataset_id: Dataset ID

        Returns:
            Ok(dict) with JSON-LD metadata, or Err(ApiFailure)
        """
        url = f"{self.base_url}/metadata/{dataset_id}/json-ld"
        return await self.get_json(url)

    async def get_organizations(self) -> Result[list[EcudoOrganization], ApiFailure]:
        """
        Fetch list of all available organizations.

        Returns:
            Ok(list) of organization dicts, or Err(ApiFailure)
        """
        result = await self.get_json(f"{self.base_url}/organizations")
        return result.map(lambda d: d.get("organizations", []))
