"""
Tap Processor

A pass-through processor that sends copies of items to a Sink.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from crawlers.core.processor import Processor, ProcessorStats
from crawlers.core.result import Ok
from crawlers.core.sink import Sink


@dataclass
class TapStats(ProcessorStats):
    """Statistics for Tap processor."""

    pushed: int = 0

    def __str__(self) -> str:
        return f"pushed: {self.pushed}"


class Tap[T](Processor[T, T, TapStats]):
    """
    Passes items through unchanged while sending a copy to a Sink.

    Use Tap to observe data flowing through a pipeline without affecting it.
    The optional `transform` function reshapes items before pushing to the sink
    (e.g. calling `.to_json()` on a model object).

    Tap does NOT manage the sink lifecycle - that is RunContext's responsibility.

    Example:
        raw_sink = JSONLSink(path)
        pipeline = ProcessorPipeline([
            ParserProcessor(parser=MyParser()),
            Tap(raw_sink, transform=lambda d: d.to_json()),
            OnedataConverter(...),
            Tap(processed_sink, transform=lambda d: d.to_json()),
        ])
    """

    def __init__(
        self,
        sink: Sink,
        transform: Callable[[T], Any] | None = None,
        enabled: bool = True,
    ):
        """
        Initialize tap.

        Args:
            sink: Destination sink to push items to
            transform: Optional function to reshape items before pushing.
                       If None, items are pushed as-is.
            enabled: Whether this processor is active
        """
        super().__init__(enabled=enabled)
        self.sink = sink
        self.transform = transform

    def describe(self) -> str:
        """Return description with sink info."""
        return f"Tap -> {self.sink}"

    def artifacts(self) -> list[Path]:
        """Delegate to sink."""
        return self.sink.artifacts()

    def _create_stats(self) -> TapStats:
        """Create tap-specific stats."""
        return TapStats()

    async def process(self, item: T) -> Ok[T]:
        """
        Push item to sink and pass it through unchanged.

        Args:
            item: Input item

        Returns:
            Ok(item), unmodified
        """
        data = self.transform(item) if self.transform else item
        await self.sink.push(data)
        self._stats.pushed += 1
        self._stats.processed += 1
        return Ok(item)
