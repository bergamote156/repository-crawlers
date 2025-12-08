"""
Data Conversion Processors

Processors that convert between data formats.
"""

from typing import TYPE_CHECKING

from ecudo.models.onedata import OnedataDataset, OnedataFile
from ecudo.models.record import EcudoRecord
from ecudo.processors.base import Processor

if TYPE_CHECKING:
    from ecudo.serializers.base import MetadataSerializer


class OnedataConverter(Processor[EcudoRecord, OnedataDataset]):
    """
    Converts EcudoRecord to OnedataDataset.

    Uses a metadata serializer to generate XML metadata
    and builds the final structure for Onedata registration.
    """

    def __init__(self, serializer: "MetadataSerializer"):
        """
        Initialize converter.

        Args:
            serializer: Metadata serializer for XML generation
        """
        self.serializer = serializer
        self._converted = 0

    async def process(self, record: EcudoRecord) -> OnedataDataset | None:
        """
        Convert EcudoRecord to OnedataDataset.

        Args:
            record: Parsed eCUDO record

        Returns:
            OnedataDataset ready for registration
        """
        dataset = OnedataDataset(
            name=record.title,
            location=record.title.replace("/", "-"),
            pid=record.identifier,
            metadata_xml=self.serializer.serialize(record),
            files=[
                OnedataFile(name=f.name, url=f.url, path=f.name) for f in record.files
            ],
        )

        self._converted += 1
        return dataset

    def get_stats(self) -> dict:
        """Return converter statistics."""
        return {"converted": self._converted}

    async def close(self) -> None:
        """Print conversion statistics."""
        if self._converted > 0:
            print("\n📊 Onedata Converter Statistics:")
            print(f"   Converted: {self._converted}")
