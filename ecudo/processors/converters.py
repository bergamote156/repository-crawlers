"""
Data Conversion Processors

Processors that convert between data formats.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from collections import Counter
from typing import Callable
from urllib.parse import urlparse

from ecudo import output
from ecudo.models.ecudo import EcudoDataset, EcudoFile
from ecudo.models.onedata import OnedataDataset, OnedataFile
from ecudo.processors.base import Processor


class OnedataConverter(Processor[EcudoDataset, OnedataDataset]):
    """
    Converts EcudoDataset to OnedataDataset.

    Uses a metadata generator function to produce XML metadata
    and builds the final structure for Onedata registration.
    """

    def __init__(self, metadata_generator: Callable[[EcudoDataset], str]):
        """
        Initialize converter.

        Args:
            metadata_generator: Function that generates XML metadata from EcudoDataset
                                (e.g., ecudo.metadata.openaire.generate_xml)
        """
        self.metadata_generator = metadata_generator
        self._converted = 0

    async def process(self, item: EcudoDataset) -> OnedataDataset | None:
        """
        Convert EcudoDataset to OnedataDataset.

        Args:
            item: eCUDO dataset

        Returns:
            OnedataDataset ready for registration
        """
        # Resolve path collisions when multiple files have the same filename
        paths = resolve_path_collisions(item.files)

        dataset = OnedataDataset(
            name=item.title,
            location=item.title.replace("/", "-"),
            pid=item.identifier,
            metadata_xml=self.metadata_generator(item),
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
            output.stats("\n📊 Onedata Converter Statistics:")
            output.stats(f"   Converted: {self._converted}")


def resolve_path_collisions(files: list[EcudoFile]) -> list[str]:
    """
    Generate unique paths for files, resolving collisions using URL structure.

    When multiple files have the same filename, progressively add more
    path segments from the URL until all paths are unique.

    Example:
        URLs:
        - https://example.com/api/stats/hl/2023/data.csv
        - https://example.com/api/raw/hl/2023/data.csv

        Initial paths: ["data.csv", "data.csv"] (collision!)
        After resolution: ["stats/hl/2023/data.csv", "raw/hl/2023/data.csv"]

    Args:
        files: List of FileInfo objects with URLs

    Returns:
        List of unique paths corresponding to each file
    """
    if not files:
        return []

    files_num = len(files)

    max_path_segments_num = 1
    path_segments_per_file = {}
    used_path_segments_num_per_file = {}
    unresolved_files = set()

    for idx in range(files_num):
        file_path_segments = _get_path_segments(files[idx].url)
        path_segments_per_file[idx] = file_path_segments
        used_path_segments_num_per_file[idx] = 1
        unresolved_files.add(idx)
        max_path_segments_num = max(max_path_segments_num, len(file_path_segments))

    for _ in range(max_path_segments_num):
        counter: Counter[str] = Counter()
        paths: dict[int, str] = {}
        for idx in unresolved_files:
            file_path = _build_path_from_segments(
                path_segments_per_file[idx], used_path_segments_num_per_file[idx]
            )
            paths[idx] = file_path
            counter.update([file_path])

        # Find paths that still have collisions
        colliding_paths = {
            path for path, collisions in counter.items() if collisions > 1
        }

        # Update unresolved set
        new_unresolved_files = set()
        for idx in unresolved_files:
            if paths[idx] in colliding_paths:
                # Try to add more segments if available
                if used_path_segments_num_per_file[idx] < len(
                    path_segments_per_file[idx]
                ):
                    used_path_segments_num_per_file[idx] += 1
                    new_unresolved_files.add(idx)

        if not new_unresolved_files:
            break
        unresolved_files = new_unresolved_files
    else:
        output.warning(
            f"Colliding paths found: {[files[i].url for i in unresolved_files]}"
        )

    # Build final paths
    return [
        _build_path_from_segments(
            path_segments_per_file[i], used_path_segments_num_per_file[i]
        )
        for i in range(len(files))
    ]


def _get_path_segments(url: str) -> list[str]:
    """Extract path segments from URL (reversed, filename first)."""
    try:
        path = urlparse(url).path
        return [seg for seg in path.split("/") if seg][::-1]
    except (ValueError, AttributeError):
        return []


def _build_path_from_segments(segments: list[str], count: int) -> str:
    """
    Build a path from the last N URL segments.

    Args:
        segments: URL path segments in reversed order (filename first)
        count: Number of segments to use

    Returns:
        Path string with segments joined by "/"
    """
    used = segments[:count]
    return "/".join(reversed(used))
