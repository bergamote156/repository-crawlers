"""
Data Fetching Processors

Processors that fetch data from external sources.
"""

from typing import TYPE_CHECKING, Callable

from ecudo.models.record import EcudoRecord
from ecudo.processors.base import Processor

if TYPE_CHECKING:
    from ecudo.ecudo_api.client import EcudoClient


class MetadataFetcher(Processor[str, EcudoRecord]):
    """
    Fetches and parses metadata for a record ID.

    Combines HTTP fetching with JSON-LD parsing into a single
    pipeline step.
    """

    def __init__(
        self, client: "EcudoClient", parser: Callable[[dict], EcudoRecord | None]
    ):
        """
        Initialize metadata fetcher.

        Args:
            client: EcudoClient for HTTP requests
            parser: Callable for JSON-LD parsing
        """
        self.client = client
        self.parser = parser
        self._fetched = 0
        self._parsed = 0
        self._failed = 0

    async def process(self, item: str) -> EcudoRecord | None:
        """
        Fetch and parse metadata for a record.

        Args:
            item: URN identifier of the record

        Returns:
            Parsed EcudoRecord or None if fetch/parse failed
        """
        raw = await self.client.get_record_metadata(item)

        if not raw:
            self._failed += 1
            return None

        self._fetched += 1

        record = self.parser(raw)
        if record:
            self._parsed += 1
        else:
            self._failed += 1

        return record

    def get_stats(self) -> dict:
        """Return fetcher statistics."""
        return {
            "fetched": self._fetched,
            "parsed": self._parsed,
            "failed": self._failed,
        }

    async def close(self) -> None:
        """Print fetch statistics."""
        total = self._fetched + self._failed
        if total > 0:
            print("\n📊 Metadata Fetcher Statistics:")
            print(f"   Fetched: {self._fetched}")
            print(f"   Parsed: {self._parsed}")
            print(f"   Failed: {self._failed}")
