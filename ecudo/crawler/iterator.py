"""
eCUDO Record ID Iterator

Async iterator that yields record IDs from an organization.
Lightweight - fetches only IDs (small payloads), not full metadata.
"""

from typing import AsyncIterator, Optional

from ecudo.crawler.client import EcudoClient


class RecordIDIterator:
    """
    Async iterator yielding record IDs from an eCUDO organization.

    This iterator is lightweight - it only fetches record IDs (small payloads).
    The actual metadata fetching should be done by workers in parallel.

    Usage:
        async with EcudoClient() as client:
            iterator = RecordIDIterator(client, "iopan", max_records=100)
            async for record_id in iterator:
                # Process record_id
                pass
    """

    def __init__(
        self,
        client: EcudoClient,
        org_id: str,
        page_size: int = 200,
        max_records: Optional[int] = None,
    ):
        """
        Initialize the iterator.

        Args:
            client: EcudoClient instance (must be in async context)
            org_id: Organization ID to crawl
            page_size: Number of IDs per page request
            max_records: Maximum number of records to yield (None = all)
        """
        self.client = client
        self.org_id = org_id
        self.page_size = page_size
        self.max_records = max_records
        self._yielded = 0
        self._page = 0

    def __aiter__(self) -> AsyncIterator[str]:
        """Return self as async iterator."""
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[str]:
        """
        Async generator yielding record IDs.

        Fetches pages of IDs sequentially and yields them one by one.
        Stops when no more IDs or max_records reached.
        """
        self._yielded = 0
        self._page = 0

        while True:
            # Fetch next page of IDs
            offset = self._page * self.page_size + 1
            ids = await self.client.get_record_ids_page(
                self.org_id, offset, self.page_size
            )

            if not ids:
                # No more records
                break

            # Yield IDs one by one
            for record_id in ids:
                yield record_id
                self._yielded += 1

                if self.max_records and self._yielded >= self.max_records:
                    print(f"📄 Reached max_records limit: {self.max_records}")
                    return

            self._page += 1
            print(f"📄 Page {self._page} | {self._yielded} IDs fetched")

        print(f"📦 ID iteration complete. Total: {self._yielded}")

    @property
    def yielded_count(self) -> int:
        """Number of IDs yielded so far."""
        return self._yielded

    @property
    def pages_fetched(self) -> int:
        """Number of pages fetched so far."""
        return self._page
