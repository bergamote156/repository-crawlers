"""
Writer Processors

Processors that write data to files or other destinations.
"""

import asyncio
import json
from pathlib import Path

# Import for type hints
from typing import TYPE_CHECKING, Any

from ecudo import output
from ecudo.processors.base import Processor

if TYPE_CHECKING:
    from ecudo.models.record import EcudoRecord


class JSONLWriter[T](Processor[T, T]):
    """
    Writes records to a JSONL (JSON Lines) file.

    Each record is written as a single JSON line. Thread-safe
    for concurrent writes using asyncio.Lock.

    Generic over input type T - will call to_json() if available,
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
            output.stats(f"📝 Wrote {self._written} records to {self.filepath}")

    async def process(self, item: T) -> T | None:
        """
        Write record to file.

        Args:
            item: Object to write as JSON line (dict or object with to_json())

        Returns:
            Same item (pass-through)
        """
        if not self._file:
            raise RuntimeError("Writer not opened. Call open() first.")

        # Convert to dict if needed
        if hasattr(item, "to_json"):
            data = item.to_json()
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
