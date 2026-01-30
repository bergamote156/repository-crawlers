"""
Ecudo API Client.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass
from typing import AsyncIterator, TypedDict

from crawlers.core.abc.api import ApiClient
from crawlers.core.ui import console


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
            ids = await self.list_dataset_ids(opts.org_id, offset, opts.page_size)

            if not ids:
                break

            for dataset_id in ids:
                yield dataset_id
                yielded += 1

                if opts.max_datasets and yielded >= opts.max_datasets:
                    console.info(f"Reached max_datasets limit: {opts.max_datasets}")
                    return

            page += 1
            console.info(f"📄 Page {page} | {yielded} IDs fetched")

        console.info(f"ID iteration complete. Total: {yielded}")

    async def list_dataset_ids(self, org_id: str, offset: int, limit: int) -> list[str]:
        """
        Fetch a page of dataset IDs.

        Args:
            org_id: Organization ID
            offset: Pagination offset (1-based)
            limit: Number of items per page

        Returns:
            List of dataset IDs
        """
        url = (
            f"{self.base_url}/organizations/{org_id}/data?offset={offset}&limit={limit}"
        )
        data = await self.get_json(url)
        return data.get("metadata", [])

    async def get_dataset_metadata(self, dataset_id: str) -> dict:
        """
        Fetch full JSON-LD metadata for a dataset.

        Args:
            dataset_id: Dataset ID

        Returns:
            Dictionary with JSON-LD metadata
        """
        url = f"{self.base_url}/metadata/{dataset_id}/json-ld"
        return await self.get_json(url)

    async def get_organizations(self) -> list[EcudoOrganization]:
        """
        Fetch list of all available organizations.

        Returns:
            List of organization dicts with 'id', 'name', 'link' keys
        """
        data = await self.get_json(f"{self.base_url}/organizations")
        return data.get("organizations", [])
