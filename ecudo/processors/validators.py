"""
Validation Processors

Processors that validate dataset records.
"""

from pathlib import Path
from typing import Optional

from ecudo import output
from ecudo.ecudo_api.client import EcudoClient
from ecudo.models.ecudo import EcudoDataset
from ecudo.processors.base import Processor
from ecudo.processors.writers import JSONLWriter


class URLValidator(Processor[EcudoDataset, EcudoDataset]):
    """
    Validates that all file URLs in a record are accessible.

    Uses HEAD requests to check URL accessibility. Records with
    any inaccessible URLs are filtered out. Optionally logs
    invalid URLs to a JSONL file for later inspection.

    Note: This processor requires an EcudoClient for HTTP requests.
    The client must be in an async context when the processor runs.
    """

    def __init__(
        self,
        client: EcudoClient,
        invalid_url_log: str | Path | None = None,
    ):
        """
        Initialize URL validator.

        Args:
            client: EcudoClient instance for HTTP requests
            invalid_url_log: Optional path to JSONL file for invalid URLs
        """
        self.client = client
        self.invalid_url_log = Path(invalid_url_log) if invalid_url_log else None
        self._validated = 0
        self._failed = 0
        self._logged = 0
        self._log_writer: JSONLWriter[dict] | None = None

    async def open(self) -> None:
        """Prepare optional invalid-URL log."""
        if self.invalid_url_log:
            self._log_writer = JSONLWriter(self.invalid_url_log, show_stats=False)
            await self._log_writer.open()
            self._logged = 0

    async def process(self, item: EcudoDataset) -> Optional[EcudoDataset]:
        """
        Validate all file URLs in the record.

        Args:
            item: Dataset record to validate

        Returns:
            Record if all URLs valid, None if any URL is invalid
        """
        for file_info in item.files:
            is_valid = await self.client.validate_url(file_info.url)

            if not is_valid:
                self._failed += 1
                output.debug(
                    f"⚠️ Invalid URL in {item.identifier[:50]}: {file_info.url}"
                )
                if self._log_writer:
                    await self._log_writer.process(
                        {"identifier": item.identifier, "url": file_info.url}
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

        total = self._validated + self._failed
        if total > 0:
            output.stats("\n📊 URL Validator Statistics:")
            output.stats(f"   Validated: {self._validated}")
            output.stats(f"   Failed: {self._failed}")
            output.stats(f"   Pass rate: {self._validated / total:.1%}")
            if self.invalid_url_log and self._logged > 0:
                output.stats(
                    f"   Logged {self._logged} invalid URLs to {self.invalid_url_log}"
                )
