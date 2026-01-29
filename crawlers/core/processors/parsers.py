"""
Data Parsing Processors

Processors that parse raw data into structured models.
"""

# pylint: disable=too-few-public-methods

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass
from typing import Protocol

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
class ParserStats(ProcessorStats):
    """Statistics for ParserProcessor."""

    parsed: int = 0

    def __str__(self) -> str:
        return f"parsed: {self.parsed}, failed: {self.failed}"


class ParserProcessor[RawT, DatasetT](Processor[RawT, DatasetT, ParserStats]):
    """
    Parses raw data (e.g. dict) into a dataset model.

    Useful for APIs that return full records in search results
    (like STAC) rather than just IDs.
    """

    def __init__(
        self,
        parser: Parser[RawT, DatasetT],
        enabled: bool = True,
    ):
        """
        Initialize parser processor.

        Args:
            parser: Parser instance/protocol to convert raw to dataset
            enabled: Whether this processor is active
        """
        super().__init__(enabled=enabled)
        self.parser = parser

    def describe(self) -> str:
        """Return description with parser name."""
        parser_name = type(self.parser).__name__
        return f"ParserProcessor: parse with {parser_name}"

    def _create_stats(self) -> ParserStats:
        """Create parser-specific stats."""
        return ParserStats()

    async def process(self, item: RawT) -> DatasetT | None:
        """
        Parse raw data into dataset model.

        Args:
            item: Raw data (e.g. dict)

        Returns:
            Parsed dataset or None if failed/skipped
        """
        dataset = self.parser.parse(item)

        if dataset:
            self._stats.parsed += 1
            self._stats.processed += 1
        else:
            self._stats.failed += 1

        return dataset
