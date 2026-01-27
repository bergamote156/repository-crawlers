"""
Writers Processors

Processors for writing data to various outputs.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import json
from pathlib import Path
from typing import Protocol, TextIO, cast, runtime_checkable

from crawlers.core.abc.processor import Processor


@runtime_checkable
class Serializable(Protocol):
    """Protocol for objects that can be converted to a JSON."""

    def to_json(self) -> dict:
        """Convert object to JSON dictionary."""
        ...


class JSONLWriter[T: dict | Serializable](Processor[T, T]):
    """
    Writes items to a JSONL file.

    Passes items through unchanged.
    Supports items that are either dictionaries or objects with a `to_json()` method.
    """

    def __init__(self, output_path: Path):
        """
        Initialize the writer.

        Args:
            output_path: Path to the output JSONL file
        """
        self.output_path = output_path
        self._file: TextIO | None = None

    async def open(self) -> None:
        """Open the output file."""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        # pylint: disable=consider-using-with
        self._file = open(self.output_path, "a", encoding="utf-8")

    async def process(self, item: T) -> T:
        """
        Write item to file and pass it through.

        Args:
            item: Item to write

        Returns:
            The same item
        """
        if self._file:
            if isinstance(item, Serializable):
                data = item.to_json()
            else:
                # Type checker knows it must be a dict due to T: dict | Serializable
                data = cast(dict, item)

            json_str = json.dumps(data, ensure_ascii=False)
            self._file.write(json_str + "\n")
            self._file.flush()  # Ensure data is written

        return item

    async def close(self) -> None:
        """Close the output file."""
        if self._file:
            self._file.close()
            self._file = None
