"""
Filter Processors

Processors for filtering data.
"""

# pylint: disable=too-few-public-methods

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import difflib
from dataclasses import dataclass
from typing import Protocol

from crawlers.core.processor import Processor, ProcessorStats
from crawlers.core.result import Err, Ok, Result


class Dataset(Protocol):
    """Dataset object required properties by DiversityFilter."""

    identifier: str
    title: str


@dataclass
class DiversityFilterStats(ProcessorStats):
    """Statistics for DiversityFilter."""

    groups_count: int = 0

    def __str__(self) -> str:
        return f"{self.processed} passed, {self.filtered} filtered, {self.groups_count} groups"


class DiversityFilter[DatasetT: Dataset](
    Processor[DatasetT, DatasetT, DiversityFilterStats]
):
    """
    Filters out datasets with similar titles to ensure diversity.

    Groups datasets by similar titles and limits the number of datasets per group.
    """

    def __init__(
        self,
        max_similar: int = 10,
        similarity_threshold: float = 0.85,
        enabled: bool = True,
    ):
        """
        Initialize diversity filter.

        Args:
            max_similar: Maximum number of similar datasets allowed
            similarity_threshold: Threshold for title similarity (0.0-1.0)
            enabled: Whether this processor is active
        """
        super().__init__(enabled=enabled)
        self.max_similar = max_similar
        self.similarity_threshold = similarity_threshold
        # Stores indices of representative titles for groups
        self._groups: list[list[str]] = []
        # Count of datasets in each group
        self._group_counts: list[int] = []

    def describe(self) -> str:
        """Return description with filter parameters."""
        return (
            f"DiversityFilter: max {self.max_similar} similar "
            f"({self.similarity_threshold:.0%} threshold)"
        )

    def _create_stats(self) -> DiversityFilterStats:
        """Create filter-specific stats."""
        return DiversityFilterStats()

    async def process(self, item: DatasetT) -> Result[DatasetT, dict]:
        """
        Check if dataset is too similar to existing ones.

        Args:
            item: Dataset to check

        Returns:
            Ok(dataset) if it passes, Err(reason) if filtered
        """
        title = item.title

        for idx, representatives in enumerate(self._groups):
            rep_title = representatives[0]
            similarity = difflib.SequenceMatcher(None, title, rep_title).ratio()

            if similarity >= self.similarity_threshold:
                if self._group_counts[idx] >= self.max_similar:
                    self._stats.filtered += 1
                    return Err(
                        {
                            "dataset_id": item.identifier,
                            "reason": "filtered_duplicate",
                            "detail": {
                                "similar_to": rep_title,
                                "similarity": round(similarity, 3),
                            },
                            "processor": "DiversityFilter",
                        }
                    )

                self._group_counts[idx] += 1
                self._stats.processed += 1
                return Ok(item)

        # No matching group found, start a new one
        self._groups.append([title])
        self._group_counts.append(1)
        self._stats.groups_count += 1
        self._stats.processed += 1
        return Ok(item)
