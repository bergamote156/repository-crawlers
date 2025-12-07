"""
Validation Processors

Processors that validate dataset records.
"""

from typing import Optional

from ecudo.crawler.client import EcudoClient
from ecudo.models.record import EcudoRecord
from ecudo.processors.base import Processor


class URLValidator(Processor[EcudoRecord, EcudoRecord]):
    """
    Validates that all file URLs in a record are accessible.

    Uses HEAD requests to check URL accessibility. Records with
    any inaccessible URLs are filtered out.

    Note: This processor requires an EcudoClient for HTTP requests.
    The client must be in an async context when the processor runs.
    """

    def __init__(self, client: EcudoClient):
        """
        Initialize URL validator.

        Args:
            client: EcudoClient instance for HTTP requests
        """
        self.client = client
        self._validated = 0
        self._failed = 0

    async def process(self, record: EcudoRecord) -> Optional[EcudoRecord]:
        """
        Validate all file URLs in the record.

        Args:
            record: Dataset record to validate

        Returns:
            Record if all URLs valid, None if any URL is invalid
        """
        for file_info in record.files:
            is_valid = await self.client.validate_url(file_info.url)

            if not is_valid:
                self._failed += 1
                print(f"⚠️ Invalid URL in {record.identifier[:50]}: {file_info.url}")
                return None

        self._validated += 1
        return record

    async def close(self) -> None:
        """Print validation statistics."""
        total = self._validated + self._failed
        if total > 0:
            print(f"\n📊 URL Validator Statistics:")
            print(f"   Validated: {self._validated}")
            print(f"   Failed: {self._failed}")
            print(f"   Pass rate: {self._validated / total:.1%}")
