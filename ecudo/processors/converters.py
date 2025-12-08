"""
Data Conversion Processors

Processors that convert between data formats.
"""

from typing import Callable

from ecudo.models.onedata import OnedataDataset, OnedataFile
from ecudo.models.record import EcudoRecord
from ecudo.processors.base import Processor


class OnedataConverter(Processor[EcudoRecord, OnedataDataset]):
    """
    Converts EcudoRecord to OnedataDataset.

    Uses a metadata generator function to produce XML metadata
    and builds the final structure for Onedata registration.
    """

    def __init__(self, metadata_generator: Callable[[EcudoRecord], str]):
        """
        Initialize converter.

        Args:
            metadata_generator: Function that generates XML metadata from EcudoRecord
                              (e.g., ecudo.metadata.openaire.generate_xml)
        """
        self.metadata_generator = metadata_generator
        self._converted = 0

    async def process(self, item: EcudoRecord) -> OnedataDataset | None:
        """
        Convert EcudoRecord to OnedataDataset.

        Args:
            item: Parsed eCUDO record

        Returns:
            OnedataDataset ready for registration
        """
        dataset = OnedataDataset(
            name=item.title,
            location=item.title.replace("/", "-"),
            pid=item.identifier,
            metadata_xml=self.metadata_generator(item),
            files=[
                OnedataFile(name=f.name, url=f.url, path=f.name) for f in item.files
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
