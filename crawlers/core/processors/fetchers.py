"""
Data Fetching Processors

Processors that fetch data from external sources.
"""

# pylint: disable=too-few-public-methods

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

from crawlers.core.abc.processor import Processor, ProcessorStats


class Parser[I, O](Protocol):
    """
    Protocol for data parsers.

    Plugins can implement this protocol or use a simple callable.
    Fetchers accept anything that has a `parse()` method (duck typing).

    Generics:
        I: Type of raw data (e.g. dict from JSON)
        O: Type of output model (e.g. EcudoDataset)
    """

    def parse(self, raw: I) -> O | None:
        """
        Parse raw data into a dataset model.

        Args:
            raw: Raw data from API

        Returns:
            Parsed model or None if data is invalid/skipped
        """


@dataclass
class FetcherStats(ProcessorStats):
    """Statistics for DatasetFetcher."""

    fetched: int = 0
    parsed: int = 0

    def __str__(self) -> str:
        return f"fetched: {self.fetched}, parsed: {self.parsed}, failed: {self.failed}"


class DatasetFetcher[RawT, DatasetT](Processor[str, DatasetT, FetcherStats]):
    """
    Fetches and parses metadata for a dataset ID.

    Combines fetching raw data (via a callable) and parsing it (via a Parser).
    Suitable for APIs where listing IDs is separate from fetching full details.
    """

    def __init__(
        self,
        fetch_fn: Callable[[str], Awaitable[RawT]],
        parser: Parser[RawT, DatasetT],
    ):
        """
        Initialize fetcher.

        Args:
            fetch_fn: Async function taking ID and returning raw I
            parser: Parser instance/protocol to convert I to O
        """
        super().__init__()
        self.fetch_fn = fetch_fn
        self.parser = parser

    def _create_stats(self) -> FetcherStats:
        """Create fetcher-specific stats."""
        return FetcherStats()

    async def process(self, item: str) -> DatasetT | None:
        """
        Fetch and parse metadata for a dataset ID.

        Args:
            item: Dataset identifier

        Returns:
            Parsed dataset or None if failed/skipped
        """
        raw = await self.fetch_fn(item)

        if not raw:
            self._stats.failed += 1
            return None

        self._stats.fetched += 1

        dataset = self.parser.parse(raw)
        if dataset:
            self._stats.parsed += 1
            self._stats.processed += 1
        else:
            self._stats.failed += 1  # Parsed as None (invalid/skipped)

        return dataset
