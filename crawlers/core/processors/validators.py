"""
Validation Processors

Processors for validating data.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Protocol, Sequence

from crawlers.core.abc.processor import Processor, ProcessorStats
from crawlers.core.processors.writers import JSONLWriter


class DatasetFile(Protocol):
    # pylint: disable=too-few-public-methods
    """Dataset file object required properties by URLValidator."""

    url: str


class Dataset(Protocol):
    # pylint: disable=too-few-public-methods
    """Dataset object required properties by URLValidator."""

    identifier: str
    files: Sequence[DatasetFile]


@dataclass
class URLValidatorStats(ProcessorStats):
    """Statistics for URLValidator."""

    invalid_logged: int = 0

    def __str__(self) -> str:
        total = self.processed + self.filtered
        rate = f"{self.processed / total:.1%}" if total > 0 else "N/A"
        base = f"valid: {self.processed}, invalid: {self.filtered}, pass rate: {rate}"
        if self.invalid_logged:
            base += f", logged: {self.invalid_logged}"
        return base


class URLValidator[DatasetT: Dataset](Processor[DatasetT, DatasetT, URLValidatorStats]):
    """
    Validates accessibility of file URLs in a dataset.

    Uses `files` attribute of InputDataset.
    """

    def __init__(
        self,
        validate_fn: Callable[[str], Awaitable[bool]],
        invalid_url_log: Path | None = None,
        enabled: bool = True,
    ):
        """
        Initialize validator.

        Args:
            validate_fn: Async function taking URL and returning True if valid
            invalid_url_log: Optional path to log invalid URLs to
            enabled: Whether this processor is active
        """
        super().__init__(enabled=enabled)
        self.validate_fn = validate_fn
        self.invalid_url_log = invalid_url_log
        self._log_writer: "JSONLWriter[dict] | None" = None

    def describe(self) -> str:
        """Return description with log path if configured."""
        log_note = f" (log: {self.invalid_url_log})" if self.invalid_url_log else ""
        return f"URLValidator: check URL accessibility{log_note}"

    def artifacts(self) -> list[Path]:
        """Return invalid URL log file if configured."""
        if self.invalid_url_log:
            return [self.invalid_url_log]
        return []

    def _create_stats(self) -> URLValidatorStats:
        """Create validator-specific stats."""
        return URLValidatorStats()

    async def open(self) -> None:
        """Prepare optional invalid-URL log."""
        if self.invalid_url_log:
            self._log_writer = JSONLWriter(self.invalid_url_log)
            await self._log_writer.open()

    async def process(self, item: DatasetT) -> DatasetT | None:
        """
        Validate all file URLs in the dataset.

        If any file URL is invalid, the dataset is considered invalid.

        Args:
            item: Dataset to validate

        Returns:
            Dataset if all URLs are valid, None otherwise
        """
        valid_dataset = True
        failed_url = ""

        # Validate all files
        for file in item.files:
            if not await self.validate_fn(file.url):
                valid_dataset = False
                failed_url = file.url
                break

        if not valid_dataset:
            self._stats.filtered += 1
            if self._log_writer:
                await self._log_writer.process(
                    {"identifier": item.identifier, "url": failed_url}
                )
                self._stats.invalid_logged += 1

            return None

        self._stats.processed += 1
        return item

    async def close(self) -> None:
        """Close log file if used."""
        if self._log_writer:
            await self._log_writer.close()
            self._log_writer = None
