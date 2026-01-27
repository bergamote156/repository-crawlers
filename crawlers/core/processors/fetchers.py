"""
Data Fetching Processors

Processors that fetch data from external sources.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from typing import Awaitable, Callable, Protocol

from crawlers.core import output
from crawlers.core.abc.processor import Processor


class Parser[RawDatasetT, DatasetT](Protocol):
    """
    Protocol for data parsers.

    Plugins can implement this protocol or use a simple callable.
    Fetchers accept anything that has a `parse()` method (duck typing).

    Generics:
        RawDatasetT: Type of raw data (e.g. dict from JSON)
        DatasetT: Type of output model (e.g. EcudoDataset)
    """

    def parse(self, raw: RawDatasetT) -> DatasetT | None:
        """
        Parse raw data into a dataset model.

        Args:
            raw: Raw data from API

        Returns:
            Parsed model or None if data is invalid/skipped
        """
        ...


class DatasetFetcher[RawDatasetT, DatasetT](Processor[str, DatasetT]):
    """
    Fetches and parses metadata for a dataset ID.

    Combines fetching raw data (via a callable) and parsing it (via a Parser).
    Suitable for APIs where listing IDs is separate from fetching full details.
    """

    def __init__(
        self,
        fetch_fn: Callable[[str], Awaitable[RawDatasetT]],
        parser: Parser[RawDatasetT, DatasetT],
    ):
        """
        Initialize fetcher.

        Args:
            fetch_fn: Async function taking ID and returning raw RawDatasetT
            parser: Parser instance/protocol to convert RawDatasetT to DatasetT
        """
        self.fetch_fn = fetch_fn
        self.parser = parser
        self._fetched = 0
        self._parsed = 0
        self._failed = 0

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
            self._failed += 1
            return None

        self._fetched += 1

        dataset = self.parser.parse(raw)
        if dataset:
            self._parsed += 1
        else:
            self._failed += 1  # Parsed as None (invalid/skipped)

        return dataset

    async def close(self) -> None:
        """Print fetch statistics."""
        total = self._fetched + self._failed
        if total > 0:
            output.stats("\n📊 Metadata Fetcher Statistics:")
            output.stats(f"   Fetched: {self._fetched}")
            output.stats(f"   Parsed: {self._parsed}")
            output.stats(f"   Failed: {self._failed}")
