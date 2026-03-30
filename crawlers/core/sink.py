"""
Abstract data sink.

Base type for destinations that accept pipeline output.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from abc import ABC, abstractmethod
from pathlib import Path


class Sink[T](ABC):
    """
    Abstract base class for data sinks.

    A sink is an external destination that accepts data - a file, a database,
    a message queue, etc.

    Lifecycle is managed externally (by RunContext):
        sink = JSONLSink(path)
        await sink.open()
        await sink.push(item)   # called by Tap or processors directly
        await sink.close()
    """

    @abstractmethod
    async def open(self) -> None:
        """Initialize sink resources (open files, connections, etc.)."""

    @abstractmethod
    async def push(self, item: T) -> None:
        """
        Send an item to the sink.

        Args:
            item: Data to send to the sink
        """

    @abstractmethod
    async def close(self) -> None:
        """Release sink resources (close files, flush buffers, etc.)."""

    def artifacts(self) -> list[Path]:
        """Return output file paths produced by this sink."""
        return []
