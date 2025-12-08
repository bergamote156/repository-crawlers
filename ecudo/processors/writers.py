"""
Writer Processors

Processors that write data to files or other destinations.
"""

import asyncio
import json
from pathlib import Path

# Import for type hints
from typing import TYPE_CHECKING, Any

from ecudo.processors.base import Processor

if TYPE_CHECKING:
    from ecudo.models.record import EcudoRecord


class JSONLWriter[T](Processor[T, T]):
    """
    Writes records to a JSONL (JSON Lines) file.

    Each record is written as a single JSON line. Thread-safe
    for concurrent writes using asyncio.Lock.

    Generic over input type T - will call to_dict() if available,
    otherwise treats input as dict.
    """

    def __init__(self, filepath: str | Path):
        """
        Initialize JSONL writer.

        Args:
            filepath: Path to output JSONL file
        """
        self.filepath = Path(filepath)
        self._file: Any | None = None
        self._lock = asyncio.Lock()
        self._written = 0

    async def open(self) -> None:
        """Open file for appending."""
        # Ensure parent directory exists
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        # Persistent handle is managed via close(); context manager not used intentionally
        # pylint: disable=consider-using-with
        self._file = self.filepath.open("a", encoding="utf-8")
        self._written = 0

    async def close(self) -> None:
        """Close file."""
        if self._file:
            self._file.close()
            self._file = None

        if self._written > 0:
            print(f"📝 Wrote {self._written} records to {self.filepath}")

    async def process(self, item: T) -> T | None:
        """
        Write record to file.

        Args:
            item: Object to write as JSON line (dict or object with to_dict())

        Returns:
            Same item (pass-through)
        """
        if not self._file:
            raise RuntimeError("Writer not opened. Call open() first.")

        # Convert to dict if needed
        if hasattr(item, "to_dict"):
            data = item.to_dict()
        else:
            data = item

        async with self._lock:
            self._file.write(json.dumps(data, ensure_ascii=False) + "\n")
            self._file.flush()
            self._written += 1

        return item

    def get_stats(self) -> dict:
        """Return writer statistics."""
        return {"written": self._written}

    @property
    def written_count(self) -> int:
        """Number of records written."""
        return self._written


class RawRecordWriter(Processor["EcudoRecord", "EcudoRecord"]):
    """
    Writes raw JSON-LD data from EcudoRecord to JSONL.

    Pass-through processor that saves the original _raw data
    before further processing. Useful for debugging and data
    preservation.
    """

    def __init__(self, filepath: str | Path):
        """
        Initialize raw record writer.

        Args:
            filepath: Path to output JSONL file
        """
        self.filepath = Path(filepath)
        self._file: Any | None = None
        self._lock = asyncio.Lock()
        self._written = 0

    async def open(self) -> None:
        """Open file for appending."""
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        # Persistent handle is managed via close(); context manager not used intentionally
        # pylint: disable=consider-using-with
        self._file = self.filepath.open("a", encoding="utf-8")
        self._written = 0

    async def close(self) -> None:
        """Close file."""
        if self._file:
            self._file.close()
            self._file = None

        if self._written > 0:
            print(f"📝 Wrote {self._written} raw records to {self.filepath}")

    async def process(self, item: "EcudoRecord") -> "EcudoRecord | None":
        """
        Write raw record data to file.

        Args:
            item: EcudoRecord with _raw data

        Returns:
            Same record (pass-through)
        """
        if not self._file:
            raise RuntimeError("Writer not opened. Call open() first.")

        async with self._lock:
            self._file.write(json.dumps(item.raw, ensure_ascii=False) + "\n")
            self._file.flush()
            self._written += 1

        return item

    def get_stats(self) -> dict:
        """Return writer statistics."""
        return {"written": self._written}


class JSONWriter[T](Processor[T, T]):
    """
    Collects records and writes them as a JSON array on close.

    Unlike JSONLWriter, this buffers all records in memory and
    writes them as a single JSON array when closed. Use for
    smaller datasets where a JSON array is preferred over JSONL.
    """

    def __init__(self, filepath: str | Path, indent: int = 2):
        """
        Initialize JSON writer.

        Args:
            filepath: Path to output JSON file
            indent: JSON indentation level
        """
        self.filepath = Path(filepath)
        self.indent = indent
        self._records: list = []

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

    async def process(self, item: T) -> T | None:
        """
        Buffer record for later writing.

        Args:
            item: Object to buffer (dict or object with to_dict())

        Returns:
            Same item (pass-through)
        """
        # Convert to dict if needed
        if hasattr(item, "to_dict"):
            data = item.to_dict()
        else:
            data = item

        self._records.append(data)
        return item

    def get_stats(self) -> dict:
        """Return writer statistics."""
        return {"buffered": len(self._records)}

    @property
    def buffered_count(self) -> int:
        """Number of records buffered."""
        return len(self._records)
