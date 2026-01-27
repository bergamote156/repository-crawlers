"""
Data Conversion Processors

Processors that convert between data models.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from collections import Counter
from typing import Protocol
from urllib.parse import urlparse

from crawlers.core import output
from crawlers.core.abc.metadata import MetadataBuilder
from crawlers.core.abc.processor import Processor
from crawlers.core.onedata import OnedataDataset, OnedataFile


class DatasetFile(Protocol):
    """Dataset file object required properties by OnedataConverter."""

    name: str
    url: str


class Dataset(Protocol):
    """Dataset object required properties by OnedataConverter."""

    identifier: str
    title: str
    files: list[DatasetFile]


class OnedataConverter[T: Dataset](Processor[T, OnedataDataset]):
    """
    Converts InputDataset to OnedataDataset.

    Uses a MetadataGenerator to produce XML metadata and prepares
    file paths specifically for Onedata registration (resolving collisions).
    """

    def __init__(self, metadata_builder: MetadataBuilder[T]):
        """
        Initialize converter.

        Args:
            metadata_builder: Generator for producing metadata XML
        """
        self.metadata_builder = metadata_builder
        self._converted = 0

    async def process(self, item: T) -> OnedataDataset:
        """
        Convert input dataset to Onedata format.

        Args:
            item: Input dataset

        Returns:
            Dataset ready for registration
        """
        # Resolve path collisions when multiple files have the same filename
        paths = self._resolve_path_collisions(item.files)

        dataset = OnedataDataset(
            name=item.title,
            location=item.title.replace("/", "-"),
            pid=item.identifier,
            metadata_xml=self.metadata_builder.build(item),
            files=[
                OnedataFile(name=f.name, url=f.url, path=path)
                for f, path in zip(item.files, paths)
            ],
        )

        self._converted += 1
        return dataset

    async def close(self) -> None:
        """Print conversion statistics."""
        if self._converted > 0:
            output.stats(f"   Converted: {self._converted}")

    def _resolve_path_collisions(self, files: list[DatasetFile]) -> list[str]:
        """
        Generate unique paths for files, resolving collisions using URL structure.

        When multiple files have the same filename, progressively add more
        path segments from the URL until all paths are unique.

        Args:
            files: List of file objects

        Returns:
            List of unique paths corresponding to each file
        """
        if not files:
            return []

        files_num = len(files)
        max_segments = 1
        segments_per_file = {}
        used_segments_per_file = {}
        unresolved = set()

        for idx in range(files_num):
            url_segments = self._get_path_segments(files[idx].url)
            segments_per_file[idx] = url_segments
            used_segments_per_file[idx] = 1
            unresolved.add(idx)
            max_segments = max(max_segments, len(url_segments))

        for _ in range(max_segments):
            counter: Counter[str] = Counter()
            paths: dict[int, str] = {}

            # Generate current paths for unresolved files
            for idx in unresolved:
                path = self._build_path(
                    segments_per_file[idx], used_segments_per_file[idx]
                )
                paths[idx] = path
                counter.update([path])

            # Find collisions
            colliding = {p for p, c in counter.items() if c > 1}

            # Prepare next iteration
            next_unresolved = set()
            for idx in unresolved:
                if paths[idx] in colliding:
                    # Try more segments if available
                    if used_segments_per_file[idx] < len(segments_per_file[idx]):
                        used_segments_per_file[idx] += 1
                        next_unresolved.add(idx)

            if not next_unresolved:
                break
            unresolved = next_unresolved
        else:
            # If still unresolved loop finished
            pass

        # Build final paths
        return [
            self._build_path(segments_per_file[i], used_segments_per_file[i])
            for i in range(files_num)
        ]

    def _get_path_segments(self, url: str) -> list[str]:
        """Extract path segments from URL (reversed, filename first)."""
        try:
            path = urlparse(url).path
            return [seg for seg in path.split("/") if seg][::-1]
        except (ValueError, AttributeError):
            return []

    def _build_path(self, segments: list[str], count: int) -> str:
        """Build path from last N segments."""
        used = segments[:count]
        return "/".join(reversed(used))
