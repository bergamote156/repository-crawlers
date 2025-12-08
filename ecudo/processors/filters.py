"""
Filter Processors

Processors that filter dataset records based on various criteria.
"""

from difflib import SequenceMatcher
from typing import Optional

from ecudo.models.record import EcudoRecord
from ecudo.processors.base import Processor


class DiversityFilter(Processor[EcudoRecord, EcudoRecord]):
    """
    Filters records to ensure diversity by limiting similar titles.

    Groups records by title similarity and limits the number of records
    per group. This prevents overwhelming representation of similar
    content (e.g., many versions of the same dataset).

    Similarity is calculated using Python's SequenceMatcher.
    """

    def __init__(
        self,
        max_similar: int = 10,
        similarity_threshold: float = 0.85,
    ):
        """
        Initialize diversity filter.

        Args:
            max_similar: Maximum records with similar titles to accept per group
            similarity_threshold: Similarity ratio (0.0-1.0) to consider titles similar
                                  0.85 means 85% similar or more = same group
        """
        self.max_similar = max_similar
        self.similarity_threshold = similarity_threshold
        self._title_groups: list[dict] = []  # [{representative: str, count: int}]
        self._accepted = 0
        self._skipped = 0

    async def process(self, item: EcudoRecord) -> Optional[EcudoRecord]:
        """
        Filter record based on title diversity.

        Args:
            item: Dataset record to check

        Returns:
            Record if accepted, None if filtered for diversity
        """
        title = item.title

        if not title:
            # No title, can't filter - accept
            self._accepted += 1
            return item

        # Find matching group
        matching_group = self._find_matching_group(title)

        if matching_group:
            # Title similar to existing group
            if matching_group["count"] >= self.max_similar:
                # Group is full
                self._skipped += 1
                return None
            # Group has room
            matching_group["count"] += 1
            self._accepted += 1
            return item

        # No matching group - create new one
        self._title_groups.append({"representative": title, "count": 1})
        self._accepted += 1
        return item

    def _find_matching_group(self, title: str) -> Optional[dict]:
        """Find a group that this title belongs to."""
        for group in self._title_groups:
            similarity = _calculate_similarity(title, group["representative"])
            if similarity >= self.similarity_threshold:
                return group
        return None

    async def close(self) -> None:
        """Print diversity statistics."""
        print("\n📊 Diversity Filter Statistics:")
        print(f"   Total groups: {len(self._title_groups)}")
        print(f"   Accepted: {self._accepted}")
        print(f"   Skipped: {self._skipped}")

        if self._title_groups:
            print("   Top groups:")
            # Sort by count descending
            sorted_groups = sorted(
                self._title_groups, key=lambda g: g["count"], reverse=True
            )
            for i, group in enumerate(sorted_groups[:10], 1):
                title_preview = group["representative"][:50]
                print(f"     {i}. '{title_preview}...' ({group['count']} records)")

            if len(self._title_groups) > 10:
                print(f"     ... and {len(self._title_groups) - 10} more groups")


def _calculate_similarity(text1: str, text2: str) -> float:
    """Calculate similarity between two strings."""
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
