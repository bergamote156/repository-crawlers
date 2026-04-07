"""
Data Conversion Processors

Processors that convert between data models.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from collections import Counter
from dataclasses import dataclass
from typing import Protocol, Sequence

from crawlers.core.metadata import MetadataBuilder
from crawlers.core.onedata import OnedataDataset, OnedataFile
from crawlers.core.processor import Processor, ProcessorStats
from crawlers.core.result import Err, Ok, Result


class DatasetFile(Protocol):
    # pylint: disable=too-few-public-methods
    """Dataset file object required properties by OnedataConverter."""

    path: str
    url: str


class Dataset(Protocol):
    # pylint: disable=too-few-public-methods
    """Dataset object required properties by OnedataConverter."""

    identifier: str
    title: str
    files: Sequence[DatasetFile]


class DatasetWithMetadata[RecordT](Protocol):
    # pylint: disable=too-few-public-methods
    """Pipeline carrier exposing a typed metadata record to the converter."""

    identifier: str
    title: str
    files: Sequence[DatasetFile]
    metadata: RecordT


@dataclass
class ConverterStats(ProcessorStats):
    """Statistics for OnedataConverter."""

    def __str__(self) -> str:
        return f"converted: {self.processed}"


class OnedataConverter[DatasetT: Dataset](
    Processor[DatasetT, OnedataDataset, ConverterStats]
):
    """
    Converts an input dataset to OnedataDataset.

    Uses a MetadataBuilder to produce XML metadata. The plugin is responsible
    for providing unique, human-readable ``path`` values on each file — this
    converter only validates uniqueness and rejects datasets with duplicates.
    Plugins whose source API exposes a flat URL list can use
    ``crawlers.plugins.utils.paths.resolve_path_collisions`` to derive paths.
    """

    def __init__(
        self,
        metadata_builder: MetadataBuilder[DatasetT],
        enabled: bool = True,
    ):
        super().__init__(enabled=enabled)
        self.metadata_builder = metadata_builder

    def describe(self) -> str:
        """Return description with metadata builder name."""
        builder_name = type(self.metadata_builder).__name__
        return f"OnedataConverter: build Onedata dataset with {builder_name}"

    def _create_stats(self) -> ConverterStats:
        """Create converter-specific stats."""
        return ConverterStats()

    async def process(self, item: DatasetT) -> Result[OnedataDataset, dict]:
        """
        Convert input dataset to Onedata format.

        Rejects the dataset if file paths are not unique.
        """
        duplicates = sorted(
            {p for p, c in Counter(f.path for f in item.files).items() if c > 1}
        )
        if duplicates:
            self._stats.failed += 1
            return Err(
                {
                    "dataset_id": item.identifier,
                    "reason": "duplicate_file_paths",
                    "detail": {"paths": duplicates},
                    "processor": "OnedataConverter",
                }
            )

        dataset = OnedataDataset(
            name=item.title,
            location=item.title.replace("/", "-"),
            pid=item.identifier,
            metadata_xml=self.metadata_builder.build(item),
            files=[OnedataFile(path=f.path, url=f.url) for f in item.files],
        )

        self._stats.processed += 1
        return Ok(dataset)


class RecordOnedataConverter[RecordT, DatasetT: DatasetWithMetadata](
    Processor[DatasetT, OnedataDataset, ConverterStats]
):
    """
    Record-based variant of :class:`OnedataConverter`.

    Expects the pipeline carrier to expose a fully populated metadata record
    on ``item.metadata`` and passes that record (not the carrier) to the
    builder. This decouples builders from plugin-specific dataset shapes —
    the parser owns the source → record mapping, the builder only knows how
    to serialize the record.
    """

    def __init__(
        self,
        metadata_builder: MetadataBuilder[RecordT],
        enabled: bool = True,
    ):
        super().__init__(enabled=enabled)
        self.metadata_builder = metadata_builder

    def describe(self) -> str:
        builder_name = type(self.metadata_builder).__name__
        return f"RecordOnedataConverter: build Onedata dataset with {builder_name}"

    def _create_stats(self) -> ConverterStats:
        return ConverterStats()

    async def process(self, item: DatasetT) -> Result[OnedataDataset, dict]:
        duplicates = sorted(
            {p for p, c in Counter(f.path for f in item.files).items() if c > 1}
        )
        if duplicates:
            self._stats.failed += 1
            return Err(
                {
                    "dataset_id": item.identifier,
                    "reason": "duplicate_file_paths",
                    "detail": {"paths": duplicates},
                    "processor": "RecordOnedataConverter",
                }
            )

        dataset = OnedataDataset(
            name=item.title,
            location=item.title.replace("/", "-"),
            pid=item.identifier,
            metadata_xml=self.metadata_builder.build(item.metadata),
            files=[OnedataFile(path=f.path, url=f.url) for f in item.files],
        )

        self._stats.processed += 1
        return Ok(dataset)
