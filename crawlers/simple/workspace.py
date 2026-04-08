"""
Simple run context.

Framework-owned sinks for the `SimpleCrawlerPlugin` flow:
`processed.jsonl` (OnedataDataset records) and `rejected.jsonl`
(parse failures as JSON dicts). A plugin that wants to persist the
unparsed source payload should open its own `raw.jsonl` sink in
`SimpleCrawlerPlugin.setup`.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from pathlib import Path

from crawlers.core.workspace import RunContext
from crawlers.simple.config import SimpleCrawlConfig
from crawlers.sinks import JSONLSink


class SimpleRunContext[ConfigT: SimpleCrawlConfig](RunContext):
    """Run context with framework-managed processed/rejected sinks."""

    def __init__(self, run_dir: Path, config: ConfigT):
        super().__init__(run_dir)
        self.config: ConfigT = config
        self.processed_sink: JSONLSink = JSONLSink(run_dir / "processed.jsonl")
        self.rejection_sink: JSONLSink = JSONLSink(run_dir / "rejected.jsonl")

    async def open_sinks(self) -> None:
        """Open processed and rejection sinks."""
        await self.processed_sink.open()
        await self.rejection_sink.open()

    async def close_sinks(self) -> None:
        """Close processed and rejection sinks."""
        await self.processed_sink.close()
        await self.rejection_sink.close()
