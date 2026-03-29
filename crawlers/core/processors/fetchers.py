"""
Data Fetching Processors

Processors that fetch data from external sources.
"""

# pylint: disable=too-few-public-methods,duplicate-code

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass
from typing import Awaitable, Callable

from crawlers.core import errors
from crawlers.core.abc.processor import Processor, ProcessorStats
from crawlers.core.result import Err, Ok, Result

from .parsers import Parser


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
        fetch_fn: Callable[[str], Awaitable[Result[RawT, object]]],
        parser: Parser[RawT, DatasetT],
        enabled: bool = True,
    ):
        """
        Initialize fetcher.

        Args:
            fetch_fn: Async function taking ID and returning Result[RawT, E]
            parser: Parser instance/protocol to convert raw to dataset
            enabled: Whether this processor is active
        """
        super().__init__(enabled=enabled)
        self.fetch_fn = fetch_fn
        self.parser = parser

    def describe(self) -> str:
        """Return description with parser name."""
        parser_name = type(self.parser).__name__
        return f"DatasetFetcher: fetch and parse with {parser_name}"

    def _create_stats(self) -> FetcherStats:
        """Create fetcher-specific stats."""
        return FetcherStats()

    async def process(self, item: str) -> Result[DatasetT, object]:
        """
        Fetch and parse metadata for a dataset ID.

        Args:
            item: Dataset identifier

        Returns:
            Ok(dataset) on success, Err(reason) on failure
        """
        match await self.fetch_fn(item):
            case Ok(value=raw):
                self._stats.fetched += 1

                dataset = self.parser.parse(raw)
                if dataset:
                    self._stats.parsed += 1
                    self._stats.processed += 1
                    return Ok(dataset)

                self._stats.failed += 1
                return Err(
                    {
                        "dataset_id": item,
                        "reason": "parse_failed",
                        "processor": "DatasetFetcher",
                    }
                )

            case Err(value=err):
                self._stats.failed += 1
                return Err(
                    {
                        "dataset_id": item,
                        "reason": "fetch_failed",
                        "detail": errors.to_json(err),
                        "processor": "DatasetFetcher",
                    }
                )

            case other:
                raise errors.MatchError(other)
