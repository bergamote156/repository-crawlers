"""
Default Run Context.

Standard RunContext with raw, processed, and rejected sinks.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from pathlib import Path

from crawlers.core.sink import Sink
from crawlers.core.workspace import RunContext
from crawlers.sinks import JSONLSink, NullSink


class DefaultRunContext(RunContext):
    """
    Standard run context with raw, processed, and rejected sinks.

    Suitable for the typical crawl pipeline:
    parse -> tap(raw) -> validate/filter -> convert -> tap(processed)
    with rejection tracking.
    """

    def __init__(self, run_dir: Path, rejection_enabled: bool = True):
        """
        Initialize with standard sinks.

        Args:
            run_dir: Path to the run directory
            rejection_enabled: Whether to create rejected.jsonl
        """
        super().__init__(run_dir)
        self.raw_sink: Sink = JSONLSink(run_dir / "raw.jsonl")
        self.processed_sink: Sink = JSONLSink(run_dir / "processed.jsonl")
        self.rejection_sink: Sink = (
            JSONLSink(run_dir / "rejected.jsonl") if rejection_enabled else NullSink()
        )

    async def open_sinks(self) -> None:
        """Open raw, processed, and rejection sinks."""
        await self.raw_sink.open()
        await self.processed_sink.open()
        await self.rejection_sink.open()

    async def close_sinks(self) -> None:
        """Close raw, processed, and rejection sinks."""
        await self.raw_sink.close()
        await self.processed_sink.close()
        await self.rejection_sink.close()
