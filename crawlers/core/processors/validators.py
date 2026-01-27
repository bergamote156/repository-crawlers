"""
Validation Processors

Processors for validating data.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from pathlib import Path
from typing import Awaitable, Callable, Protocol

from crawlers.core import output
from crawlers.core.abc.processor import Processor
from crawlers.core.processors.writers import JSONLWriter


class DatasetFile(Protocol):
    """Dataset file object required properties by URLValidator."""

    url: str


class Dataset(Protocol):
    """Dataset object required properties by URLValidator."""

    identifier: str
    files: list[DatasetFile]


class URLValidator[T: Dataset](Processor[T, T]):
    """
    Validates accessibility of file URLs in a dataset.

    Uses `files` attribute of InputDataset.
    """

    def __init__(
        self,
        validate_fn: Callable[[str], Awaitable[bool]],
        invalid_url_log: Path | None = None,
    ):
        """
        Initialize validator.

        Args:
            validate_fn: Async function taking URL and returning True if valid
            invalid_url_log: Optional path to log invalid URLs to
        """
        self.validate_fn = validate_fn
        self.invalid_url_log = invalid_url_log
        self._validated = 0
        self._invalid = 0
        self._logged = 0
        self._log_writer: JSONLWriter[dict] | None = None

    async def open(self) -> None:
        """Prepare optional invalid-URL log."""
        if self.invalid_url_log:
            self._log_writer = JSONLWriter(self.invalid_url_log)
            await self._log_writer.open()
            self._logged = 0

    async def process(self, item: T) -> T | None:
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
            self._invalid += 1
            if self._log_writer:
                await self._log_writer.process(
                    {"identifier": item.identifier, "url": failed_url}
                )
                self._logged += 1

            return None

        self._validated += 1
        return item

    async def close(self) -> None:
        """Print validation statistics and close log file if used."""
        if self._log_writer:
            await self._log_writer.close()
            self._log_writer = None

        total = self._validated + self._invalid
        if total > 0:
            output.stats("\n📊 URL Validator Statistics:")
            output.stats(f"   Validated: {self._validated}")
            output.stats(f"   Failed: {self._invalid}")
            output.stats(f"   Pass rate: {self._validated / total:.1%}")
            if self.invalid_url_log and self._logged > 0:
                output.stats(
                    f"   Logged {self._logged} invalid URLs to {self.invalid_url_log}"
                )
