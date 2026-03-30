"""JSON Lines file sink."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import json
from pathlib import Path
from typing import TextIO

from crawlers.core.sink import Sink


class JSONLSink(Sink[dict]):
    """
    Writes items as JSON lines to a file.

    Opens in append mode - safe for resume (new items are appended
    to existing data from previous runs).
    Flushes after each push for crash safety.
    """

    def __init__(self, path: Path):
        """
        Initialize the sink.

        Args:
            path: Path to the output JSONL file
        """
        self.path = path
        self._file: TextIO | None = None

    async def open(self) -> None:
        """Open the output file in append mode."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # pylint: disable=consider-using-with
        self._file = open(self.path, "a", encoding="utf-8")

    async def push(self, item: dict) -> None:
        """
        Write item as a JSON line.

        Args:
            item: Dictionary to serialize and write
        """
        if self._file:
            self._file.write(json.dumps(item, ensure_ascii=False) + "\n")
            self._file.flush()

    async def close(self) -> None:
        """Close the output file."""
        if self._file:
            self._file.close()
            self._file = None

    def artifacts(self) -> list[Path]:
        """Return the JSONL file path."""
        return [self.path]

    def __repr__(self) -> str:
        return f"JSONLSink({self.path})"
