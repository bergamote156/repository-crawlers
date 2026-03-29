"""
Validation Processors

Processors for validating data.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol, Sequence

from crawlers.core import errors
from crawlers.core.abc.processor import Processor, ProcessorStats
from crawlers.core.result import Err, Ok, Result


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

    def __str__(self) -> str:
        total = self.processed + self.filtered
        rate = f"{self.processed / total:.1%}" if total > 0 else "N/A"
        return f"valid: {self.processed}, invalid: {self.filtered}, pass rate: {rate}"


class URLValidator[DatasetT: Dataset](Processor[DatasetT, DatasetT, URLValidatorStats]):
    """
    Validates accessibility of file URLs in a dataset.

    Uses `files` attribute of InputDataset.
    """

    def __init__(
        self,
        validate_fn: Callable[[str], Awaitable[Result[bool, object]]],
        enabled: bool = True,
    ):
        """
        Initialize validator.

        Args:
            validate_fn: Async function taking URL and returning Result[bool, E]
            enabled: Whether this processor is active
        """
        super().__init__(enabled=enabled)
        self.validate_fn = validate_fn

    def describe(self) -> str:
        """Return description."""
        return "URLValidator: check URL accessibility"

    def _create_stats(self) -> URLValidatorStats:
        """Create validator-specific stats."""
        return URLValidatorStats()

    async def process(self, item: DatasetT) -> Result[DatasetT, object]:
        """
        Validate all file URLs in the dataset.

        If any file URL is invalid, the dataset is rejected.

        Args:
            item: Dataset to validate

        Returns:
            Ok(dataset) if all URLs valid, Err(reason) otherwise
        """
        for file in item.files:
            result = await self.validate_fn(file.url)
            if result.is_err():
                self._stats.filtered += 1
                err = result.err()
                return Err(
                    {
                        "dataset_id": item.identifier,
                        "reason": "invalid_url",
                        "detail": {"url": file.url, "error": errors.to_json(err)},
                        "processor": "URLValidator",
                    }
                )

        self._stats.processed += 1
        return Ok(item)
