"""
Writer Processors

Processors that write data to files or other destinations.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Optional, Union

from ecudo.processors.base import Processor


class JSONLWriter(Processor[dict, dict]):
    """
    Writes records to a JSONL (JSON Lines) file.

    Each record is written as a single JSON line. Thread-safe
    for concurrent writes using asyncio.Lock.
    """

    def __init__(self, filepath: Union[str, Path]):
        """
        Initialize JSONL writer.

        Args:
            filepath: Path to output JSONL file
        """
        self.filepath = Path(filepath)
        self._file: Optional[Any] = None
        self._lock = asyncio.Lock()
        self._written = 0

    async def open(self) -> None:
        """Open file for appending."""
        # Ensure parent directory exists
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.filepath, "a", encoding="utf-8")
        self._written = 0

    async def close(self) -> None:
        """Close file."""
        if self._file:
            self._file.close()
            self._file = None

        if self._written > 0:
            print(f"📝 Wrote {self._written} records to {self.filepath}")

    async def process(self, item: dict) -> Optional[dict]:
        """
        Write record to file.

        Args:
            item: Dictionary to write as JSON line

        Returns:
            Same item (pass-through)
        """
        if not self._file:
            raise RuntimeError("Writer not opened. Call open() first.")

        async with self._lock:
            self._file.write(json.dumps(item, ensure_ascii=False) + "\n")
            self._file.flush()
            self._written += 1

        return item

    @property
    def written_count(self) -> int:
        """Number of records written."""
        return self._written


class JSONWriter(Processor[dict, dict]):
    """
    Collects records and writes them as a JSON array on close.

    Unlike JSONLWriter, this buffers all records in memory and
    writes them as a single JSON array when closed. Use for
    smaller datasets where a JSON array is preferred over JSONL.
    """

    def __init__(self, filepath: Union[str, Path], indent: int = 2):
        """
        Initialize JSON writer.

        Args:
            filepath: Path to output JSON file
            indent: JSON indentation level
        """
        self.filepath = Path(filepath)
        self.indent = indent
        self._records: list[dict] = []

    async def open(self) -> None:
        """Initialize buffer."""
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self._records = []

    async def close(self) -> None:
        """Write all records to file as JSON array."""
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self._records, f, ensure_ascii=False, indent=self.indent)

        if self._records:
            print(f"📝 Wrote {len(self._records)} records to {self.filepath}")

    async def process(self, item: dict) -> Optional[dict]:
        """
        Buffer record for later writing.

        Args:
            item: Dictionary to buffer

        Returns:
            Same item (pass-through)
        """
        self._records.append(item)

        return item

    @property
    def buffered_count(self) -> int:
        """Number of records buffered."""
        return len(self._records)
