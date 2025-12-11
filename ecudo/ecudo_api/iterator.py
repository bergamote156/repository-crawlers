"""
eCUDO Record ID Iterator

Async iterator that yields dataset IDs from an organization.
Lightweight - fetches only IDs (small payloads), not full metadata.
"""

from typing import AsyncIterator, Optional

from ecudo import output
from ecudo.ecudo_api.client import EcudoClient


# pylint: disable=too-few-public-methods
class EcudoDatasetIDIterator:
    """
    Async iterator yielding dataset IDs from an eCUDO organization.

    This iterator is lightweight - it only fetches dataset IDs (small payloads).
    The actual metadata fetching should be done by workers in parallel.

    Usage:
        async with EcudoClient() as client:
            iterator = RecordIDIterator(client, "iopan", max_datasets=100)
            async for dataset_id in iterator:
                # Process dataset_id
                pass
    """

    def __init__(
        self,
        client: EcudoClient,
        org_id: str,
        page_size: int = 200,
        max_datasets: Optional[int] = None,
    ):
        """
        Initialize the iterator.

        Args:
            client: EcudoClient instance (must be in async context)
            org_id: Organization ID to crawl
            page_size: Number of IDs per page request
            max_datasets: Maximum number of datasets to yield (None = all)
        """
        self.client = client
        self.org_id = org_id
        self.page_size = page_size
        self.max_datasets = max_datasets
        self._yielded = 0
        self._page = 0

    def __aiter__(self) -> AsyncIterator[str]:
        """Return self as async iterator."""
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[str]:
        """
        Async generator yielding dataset IDs.

        Fetches pages of IDs sequentially and yields them one by one.
        Stops when no more IDs or max_datasets reached.
        """
        self._yielded = 0
        self._page = 0

        while True:
            # Fetch next page of IDs
            offset = self._page * self.page_size + 1
            ids = await self.client.list_dataset_ids(
                self.org_id, offset, self.page_size
            )

            if not ids:
                # No more datasets
                break

            # Yield IDs one by one
            for dataset_id in ids:
                yield dataset_id
                self._yielded += 1

                if self.max_datasets and self._yielded >= self.max_datasets:
                    output.info(f"Reached max_datasets limit: {self.max_datasets}")
                    return

            self._page += 1
            output.info(f"📄 Page {self._page} | {self._yielded} IDs fetched")

        output.info(f"ID iteration complete. Total: {self._yielded}")
