"""
Data Resolving Processors

Processors that resolve partial data into full dataset records.
"""

# pylint: disable=too-few-public-methods,duplicate-code

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, assert_never

from crawlers.core.processor import Processor, ProcessorStats
from crawlers.core.result import Err, Ok, Result

from ..core import errors
from .parsers import Parser


@dataclass
class ResolverStats(ProcessorStats):
    """Statistics for DatasetResolver."""

    resolved: int = 0
    parsed: int = 0

    def __str__(self) -> str:
        return (
            f"resolved: {self.resolved}, parsed: {self.parsed}, failed: {self.failed}"
        )


class DatasetResolver[InT, RawT, DatasetT](Processor[InT, DatasetT, ResolverStats]):
    """
    Resolves partial/reference data into a full dataset record.

    Takes an input item (e.g. an ID string or a partial dict from the iterator),
    calls resolve_fn to fetch/enrich it into full raw data, then parses the
    result into a dataset model.

    Suitable for APIs where:
    - Listing returns IDs and fetching details is separate (ecudo: str -> dict)
    - Listing returns partial records that need enrichment (vip: dict -> dict+files)
    """

    def __init__(
        self,
        resolve_fn: Callable[[InT], Awaitable[Result[RawT, Any]]],
        parser: Parser[RawT, DatasetT],
        enabled: bool = True,
    ):
        """
        Initialize resolver.

        Args:
            resolve_fn: Async function that resolves input into full raw data
            parser: Parser to convert resolved raw data into a dataset model
            enabled: Whether this processor is active
        """
        super().__init__(enabled=enabled)
        self.resolve_fn = resolve_fn
        self.parser = parser

    def describe(self) -> str:
        """Return description with parser name."""
        parser_name = type(self.parser).__name__
        return f"DatasetResolver: resolve and parse with {parser_name}"

    def _create_stats(self) -> ResolverStats:
        """Create resolver-specific stats."""
        return ResolverStats()

    async def process(self, item: InT) -> Result[DatasetT, dict]:
        """
        Resolve input into full data and parse into a dataset model.

        Args:
            item: Input item (ID, partial record, etc.)

        Returns:
            Ok(dataset) on success, Err(reason) on failure
        """
        match await self.resolve_fn(item):
            case Ok(value=raw):
                self._stats.resolved += 1

                dataset = self.parser.parse(raw)
                if dataset:
                    self._stats.parsed += 1
                    self._stats.processed += 1
                    return Ok(dataset)

                self._stats.failed += 1
                return Err(
                    {
                        "dataset_id": self._extract_id(item),
                        "reason": "parse_failed",
                        "processor": "DatasetResolver",
                    }
                )

            case Err(value=err):
                self._stats.failed += 1
                return Err(
                    {
                        "dataset_id": self._extract_id(item),
                        "reason": "resolve_failed",
                        "detail": errors.to_json(err),
                        "processor": "DatasetResolver",
                    }
                )

            case other:
                assert_never(other)

    def _extract_id(self, item: InT) -> str:
        """Best-effort ID extraction from input item."""
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            return str(
                item.get("_id", item.get("id", item.get("identifier", "unknown")))
            )
        return "unknown"
