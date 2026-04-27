"""
Run context — manages run directory, state, and sinks for a crawl.

Each crawl execution gets a timestamped run directory containing:
- `config.json`    — snapshot of the resolved configuration
- `state.json`     — status, timestamps, and live stats
- `processed.jsonl` — successfully parsed datasets
- `rejected.jsonl`  — parse failures
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import json
from datetime import datetime, timezone
from pathlib import Path

from crawlers.core.jsonl import JSONLSink


def make_run_dir(workspace: Path, plugin: str, context: str) -> Path:
    """
    Generate a unique run directory path.

    Format: `<workspace>/runs/<timestamp>_<plugin>_<context>`
    """
    ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    return workspace / "runs" / f"{ts}_{plugin}_{context}"


class RunContext[ConfigT]:
    """
    Manages a single crawl run's directory, state file, and JSONL sinks.

    Lifecycle:

        ctx = RunContext(run_dir, config)
        await ctx.open(config_snapshot={...})
        ...                          # crawl writes to sinks
        await ctx.save_stats({...})  # periodic
        await ctx.close("completed") # finalizes state + closes sinks
    """

    def __init__(self, run_dir: Path, config: ConfigT):
        self.run_dir = run_dir
        self.config: ConfigT = config
        self.processed_sink: JSONLSink = JSONLSink(run_dir / "processed.jsonl")
        self.rejection_sink: JSONLSink = JSONLSink(run_dir / "rejected.jsonl")

        self._status = "pending"
        self._started_at: str | None = None
        self._stats: dict = {}

    async def open(self, config_snapshot: dict | None = None) -> None:
        """Create run directory, save config, open sinks, mark as running."""
        self.run_dir.mkdir(parents=True, exist_ok=True)

        if config_snapshot:
            (self.run_dir / "config.json").write_text(
                json.dumps(config_snapshot, indent=2, ensure_ascii=False)
            )

        self._started_at = datetime.now(timezone.utc).isoformat()
        self._write_state("running")

        await self.processed_sink.open()
        await self.rejection_sink.open()

    async def save_stats(self, stats: dict) -> None:
        """Persist current stats to state.json."""
        self._stats = stats
        self._write_state(self._status)

    async def close(self, status: str = "completed") -> None:
        """Close sinks and write final state."""
        await self.processed_sink.close()
        await self.rejection_sink.close()
        self._write_state(status)

    def _write_state(self, status: str) -> None:
        self._status = status
        data = {
            "status": status,
            "started_at": self._started_at,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "stats": self._stats,
        }
        (self.run_dir / "state.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
