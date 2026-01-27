"""
Filter Processors

Processors for filtering data.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import difflib
from typing import Protocol

from crawlers.core import output
from crawlers.core.abc.processor import Processor


class Dataset(Protocol):
    """Dataset object required properties by DiversityFilter."""

    title: str


class DiversityFilter[T: Dataset](Processor[T, T]):
    """
    Filters out datasets with similar titles to ensure diversity.

    Groups datasets by similar titles and limits the number of datasets per group.
    Uses `title` attribute of InputDataset.
    """

    def __init__(
        self,
        max_similar: int = 10,
        similarity_threshold: float = 0.85,
    ):
        """
        Initialize diversity filter.

        Args:
            max_similar: Maximum number of similar datasets allowed
            similarity_threshold: Threshold for title similarity (0.0-1.0)
        """
        self.max_similar = max_similar
        self.similarity_threshold = similarity_threshold
        # Stores indices of representative titles for groups
        self._groups: list[list[str]] = []
        # Count of datasets in each group
        self._group_counts: list[int] = []
        # Stats
        self._processed = 0
        self._filtered = 0

    async def process(self, item: T) -> T | None:
        """
        Check if dataset is too similar to existing ones.

        Args:
            item: Dataset to check

        Returns:
            Dataset if it passes the filter, None otherwise
        """
        self._processed += 1
        title = item.title

        # Check against existing groups
        for idx, representatives in enumerate(self._groups):
            # Check similarity with representative titles of the group
            # We use the first one as primary representative
            rep_title = representatives[0]
            similarity = difflib.SequenceMatcher(None, title, rep_title).ratio()

            if similarity >= self.similarity_threshold:
                # Corresponds to this group
                if self._group_counts[idx] >= self.max_similar:
                    self._filtered += 1
                    return None  # Max limit reached for this group

                self._group_counts[idx] += 1
                # Add this title as another representative if it's slightly different?
                # For simplicity, we just count it.
                return item

        # No matching group found, start a new one
        self._groups.append([title])
        self._group_counts.append(1)
        return item

    async def close(self) -> None:
        """Print filter stats."""
        if self._processed > 0:
            output.stats(
                f"   Diversity: {self._processed} processed, {self._filtered} filtered"
            )
