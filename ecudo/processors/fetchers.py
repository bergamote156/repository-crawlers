"""
Data Fetching Processors

Processors that fetch data from external sources.
"""

from typing import TYPE_CHECKING, Callable

from ecudo import output
from ecudo.models.ecudo import EcudoDataset
from ecudo.processors.base import Processor

if TYPE_CHECKING:
    from ecudo.ecudo_api.client import EcudoClient


class DatasetFetcher(Processor[str, EcudoDataset]):
    """
    Fetches and parses metadata for a dataset ID.

    Combines HTTP fetching with JSON-LD parsing into a single
    pipeline step.
    """

    def __init__(
        self, client: "EcudoClient", parser: Callable[[dict], EcudoDataset | None]
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

    async def process(self, item: str) -> EcudoDataset | None:
        """
        Fetch and parse metadata for a dataset.

        Args:
            item: URN identifier of the dataset

        Returns:
            Parsed EcudoDataset or None if fetch/parse failed
        """
        raw = await self.client.get_dataset_metadata(item)

        if not raw:
            self._failed += 1
            return None

        self._fetched += 1

        dataset = self.parser(raw)
        if dataset:
            self._parsed += 1
        else:
            self._failed += 1

        return dataset

    async def close(self) -> None:
        """Print fetch statistics."""
        total = self._fetched + self._failed
        if total > 0:
            output.stats("\n📊 Metadata Fetcher Statistics:")
            output.stats(f"   Fetched: {self._fetched}")
            output.stats(f"   Parsed: {self._parsed}")
            output.stats(f"   Failed: {self._failed}")
