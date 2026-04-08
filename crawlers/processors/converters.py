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

from crawlers.core.metadata import MetadataRecord
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
    """Pipeline carrier exposing a typed metadata record to the converter."""

    identifier: str
    title: str
    files: Sequence[DatasetFile]
    metadata_record: MetadataRecord


@dataclass
class ConverterStats(ProcessorStats):
    """Statistics for OnedataConverter."""

    def __str__(self) -> str:
        return f"converted: {self.processed}"


class OnedataConverter[DatasetT: Dataset](
    Processor[DatasetT, OnedataDataset, ConverterStats]
):
    """
    Converts a parsed pipeline carrier to `OnedataDataset`.

    The carrier must expose a typed metadata record on 'item.metadata';
    this converter passes that record (not the carrier) to the builder so
    builders stay ignorant of plugin-specific dataset shapes. The plugin is
    responsible for providing unique, human-readable 'path' values on each
    file — this converter only validates uniqueness and rejects datasets
    with duplicates. Plugins whose source API exposes a flat URL list can
    use 'crawlers.plugins.utils.paths.resolve_path_collisions' to derive
    paths.
    """

    def _create_stats(self) -> ConverterStats:
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
            metadata_xml=item.metadata_record.to_xml(),
            files=tuple(OnedataFile(path=f.path, url=f.url) for f in item.files),
        )

        self._stats.processed += 1
        return Ok(dataset)
