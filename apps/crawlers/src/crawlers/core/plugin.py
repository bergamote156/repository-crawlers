"""
Crawler plugin base class.

Combines `confline.CommandApp` (config + CLI dispatch) with the crawl
lifecycle (setup → iterate_datasets → process → after_crawl, parallel
workers, JSONL sinks).  Plugins subclass `CrawlerPlugin`, set `name` /
`description` / `config_class`, and implement `iterate_datasets` and
`process`. The `crawl` command is auto-registered; extra commands use
`@command`.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import asyncio
import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from contextlib import AsyncExitStack
from dataclasses import asdict
from pathlib import Path
from pprint import pformat
from typing import Any, ClassVar

import yaml
from rich.panel import Panel
from rich.table import Table

from confline import (
    CliSource,
    CommandApp,
    DefaultSource,
    EnvSource,
    Source,
    YamlSource,
)
from confline.sources.base import FileOrigin
from confline.spec import Command
from crawlers.core.config import CrawlConfig
from crawlers.core.dataset import DatasetValidator, OnedataDataset
from crawlers.core.http import HttpClient
from crawlers.core.result import Result
from crawlers.core.runner import CrawlStats, run_parallel_crawl
from crawlers.core.workspace import RunContext, make_run_dir
from crawlers.ui import console

# ─────────────────────────────────────────────────────────────────────────────
# CrawlerPlugin
# ─────────────────────────────────────────────────────────────────────────────


class CrawlerPlugin[RawT, ConfigT: CrawlConfig](CommandApp, ABC):
    """
    Base class for crawler plugins.

    Each plugin is a `confline.CommandApp` whose `prog` is
    `crawlers <name>`.  The `crawl` command is auto-registered on
    concrete subclasses (those that set `name`); auxiliary commands
    use `@command`.

    Not reentrant: lifecycle hooks store mutable state on `self`
    (HTTP clients, API facades).  Plugin instances in
    `REGISTERED_PLUGINS` are singletons — two concurrent crawls on
    the same instance would overwrite that state.
    """

    # confline override knobs
    env_prefix: ClassVar[str] = "CRAWLER_"
    config_option: ClassVar[tuple[str, ...]] = ("-c", "--config")

    # CrawlerPlugin contract
    name: ClassVar[str]
    description: ClassVar[str]
    config_class: ClassVar[type[CrawlConfig]] = CrawlConfig

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)  # CommandApp scans @command methods

        # Abstract intermediate classes (e.g. shared base) skip auto-wiring.
        if not isinstance(cls.__dict__.get("name"), str):
            return

        # Default `prog` → "crawlers <name>" so help/error rendering reads correctly.
        if "prog" not in cls.__dict__:
            cls.prog = f"crawlers {cls.name}"

        # Auto-register the `crawl` command unless the subclass declared its own.
        if "crawl" not in cls._commands:
            config_cls = cls.__dict__.get("config_class") or cls.config_class
            cls._commands["crawl"] = Command(
                name="crawl",
                method_name="run_crawl",
                config_class=config_cls,
                description="Crawl datasets",
            )

    # ─────────────────────────────────────────────────────────────────────────
    # CommandApp overrides
    # ─────────────────────────────────────────────────────────────────────────

    def dispatch_command(self, command: Command, config: Any) -> Any:
        """Run the handler with an `AsyncExitStack`, in `asyncio.run`."""

        async def _run() -> Any:
            async with AsyncExitStack() as stack:
                handler = getattr(self, command.method_name)
                return await handler(config, stack)

        return asyncio.run(_run())

    def build_sources(self, parsed: Any, command: Command) -> list[Source]:
        """argparse → env → scoped YAML → defaults.

        Scoped YAML reads each `-c` file's `global` /
        `plugins.<name>` / `plugins.<name>.commands.<cmd>` sections
        and exposes them as separate scopes so command-level keys
        win over plugin-level over global, matching the layout
        operators have used before the confline migration.
        """
        sources: list[Source] = [
            CliSource(parsed),
            EnvSource(os.environ, prefix=self.env_prefix),
        ]

        config_files = self.discover_config_files(parsed)
        if config_files:
            sources.append(self._build_scoped_yaml_source(config_files, command.name))

        sources.append(DefaultSource())
        return sources

    def _build_scoped_yaml_source(
        self,
        config_files: Sequence[FileOrigin],
        command_name: str,
    ) -> YamlSource:
        """Build a `YamlSource` with three scopes per file: command, plugin, global.

        Within a file, command-scope wins over plugin over global —
        matching today's `_resolve_value` order.  Across files later
        `-c` wins fully (file beats level): a later file's global
        still wins over an earlier file's command-scope.

        `scope_origins` is parallel to `scopes`: each file contributes
        three scopes that all point back at the same `FileOrigin`, so
        `--show-config` and provenance hints name the actual file.
        """
        flat_scopes: list[dict[str, Any]] = []
        flat_origins: list[FileOrigin] = []
        ordered = list(reversed(list(config_files)))  # latest file first
        for entry in ordered:
            data = yaml.safe_load(entry.path.read_text(encoding="utf-8")) or {}
            global_scope = _ensure_dict(data.get("global"))
            plugin_scope = _ensure_dict(data.get("plugins", {}).get(self.name))
            command_scope = _ensure_dict(plugin_scope.get("commands", {}).get(command_name))
            flat_scopes.extend([command_scope, plugin_scope, global_scope])
            flat_origins.extend([entry, entry, entry])

        return YamlSource(
            scopes=flat_scopes,
            files=tuple(ordered),
            scope_origins=flat_origins,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Crawl lifecycle hooks
    # ─────────────────────────────────────────────────────────────────────────

    async def setup(self, ctx: RunContext[ConfigT], stack: AsyncExitStack) -> None:
        """
        Open plugin resources (HTTP clients, credentials).

        Store them on `self` and register async context managers on
        `stack` so they are closed automatically when the crawl ends.
        """
        return None

    async def before_crawl(self, ctx: RunContext[ConfigT]) -> None:
        """Run once after `setup` and before the worker pool starts."""
        return None

    async def after_crawl(self, ctx: RunContext[ConfigT]) -> None:
        """Run once after the worker pool finishes successfully."""
        return None

    @abstractmethod
    async def iterate_datasets(self, ctx: RunContext[ConfigT]) -> AsyncIterator[RawT]:
        """Async-iterate raw items from the upstream API."""
        raise NotImplementedError
        yield  # pragma: no cover

    @abstractmethod
    async def process(self, raw: RawT, /) -> Result[OnedataDataset, Any] | None:
        """
        Convert a raw item into an `OnedataDataset`.

        Returns:
            - `Ok(dataset)`: validated by the framework, then persisted to `processed.jsonl`
            - `Err(failure)`: persisted to `rejected.jsonl`
            - `None`: silently skipped
        """
        raise NotImplementedError

    def run_context_name(self, _config: ConfigT) -> str:
        """Short identifier appended to the run directory name."""
        return "default"

    # ─────────────────────────────────────────────────────────────────────────
    # Crawl execution — auto-registered as the `crawl` command
    # ─────────────────────────────────────────────────────────────────────────

    async def run_crawl(self, config: ConfigT, stack: AsyncExitStack) -> None:
        """Execute the `crawl` command."""
        ctx = self._create_run_context(config)
        await ctx.open(
            config_snapshot={
                "plugin": self.name,
                "config": asdict(config),
            }
        )

        state: dict[str, Any] = {"status": "pending", "stats": CrawlStats()}

        async def finalize() -> None:
            await ctx.close(state["status"])
            self._print_summary(state["status"], state["stats"], ctx)

        stack.push_async_callback(finalize)
        self._print_banner(ctx)

        try:
            validator = await self._open_validator(config, stack)

            await self.setup(ctx, stack)
            await self.before_crawl(ctx)

            stats = await run_parallel_crawl(
                source_iterator=self.iterate_datasets(ctx),
                process_fn=self.process,
                validator=validator,
                processed_sink=ctx.processed_sink,
                rejection_sink=ctx.rejection_sink,
                concurrency=config.concurrency,
                queue_size=config.queue_size,
                max_items=config.max_records,
                state_callback=lambda s: ctx.save_stats(asdict(s)),
            )
            state["stats"] = stats
            await ctx.save_stats(asdict(stats))

            await self.after_crawl(ctx)
            state["status"] = "completed"

        except (KeyboardInterrupt, asyncio.CancelledError):
            state["status"] = "interrupted"
            console.warning("Interrupted by user (Ctrl+C)")

        except Exception:
            state["status"] = "failed"
            raise

    # ─────────────────────────────────────────────────────────────────────────
    # Internals
    # ─────────────────────────────────────────────────────────────────────────

    def _create_run_context(self, config: ConfigT) -> RunContext[ConfigT]:
        run_dir = make_run_dir(
            workspace=Path(config.output_dir),
            plugin=self.name,
            context=self.run_context_name(config),
        )
        return RunContext(run_dir=run_dir, config=config)

    @staticmethod
    async def _open_validator(config: CrawlConfig, stack: AsyncExitStack) -> DatasetValidator:
        """Construct the run's `DatasetValidator`, opening a HEAD-probe client when enabled."""
        if config.no_url_validation:
            return DatasetValidator()

        http = await stack.enter_async_context(HttpClient.from_config(config))
        return DatasetValidator(http=http)

    # ─────────────────────────────────────────────────────────────────────────
    # Display
    # ─────────────────────────────────────────────────────────────────────────

    def _print_banner(self, ctx: RunContext[ConfigT]) -> None:
        title = type(self).__name__
        subtitle = self.run_context_name(ctx.config)
        content = f"[header]{title}[/]\n[muted]{subtitle}[/]\n[muted]Run: {ctx.run_dir}[/]"
        console.print(Panel(content, expand=False, border_style="cyan"))
        console.newline()
        console.debug(pformat(ctx.config))

    def _print_summary(self, status: str, stats: CrawlStats, ctx: RunContext[ConfigT]) -> None:
        setup_failed = status == "failed" and stats.queued == 0

        console.newline()
        if status == "interrupted":
            console.print(Panel("[warning]:warning: Crawl Interrupted[/]", border_style="yellow"))
        elif status == "failed":
            console.print(Panel("[error]:cross_mark: Crawl Failed[/]", border_style="red"))
        else:
            console.print(
                Panel(
                    "[success]:white_check_mark: Crawl Complete[/]",
                    border_style="green",
                )
            )

        if not setup_failed:
            console.section("Crawl Statistics")
            stats_table = Table(show_header=True, header_style="bold")
            stats_table.add_column("Metric", style="cyan")
            stats_table.add_column("Count", justify="right")
            stats_table.add_row("Queued", str(stats.queued))
            stats_table.add_row("Processed", str(stats.processed))
            stats_table.add_row("Rejected", str(stats.rejected))
            stats_table.add_row("Skipped", str(stats.skipped))
            stats_table.add_row("Failed", str(stats.failed))
            console.print(stats_table)

            console.section("Output Files")
            for sink in (ctx.processed_sink, ctx.rejection_sink):
                for path in sink.artifacts():
                    console.print(f"  [muted]>[/] {path}")

        console.section("Run Directory")
        console.print(f"  {ctx.run_dir}")

        next_steps = _build_next_steps(status, stats, ctx)
        if next_steps:
            console.section("Next Steps")
            for i, step in enumerate(next_steps, 1):
                console.print(f"  {i}. {step}")


# ─────────────────────────────────────────────────────────────────────────────
# Module-private helpers
# ─────────────────────────────────────────────────────────────────────────────


def _ensure_dict(value: Any) -> dict[str, Any]:
    """Return `value` if it's a dict, else an empty dict.

    Defensive against malformed YAML where a key appears but its
    value is `None` or a non-mapping — keeps `_walk` in YamlSource
    from tripping over a `NoneType` cursor.
    """
    return value if isinstance(value, dict) else {}


def _build_next_steps(status: str, stats: CrawlStats, ctx: RunContext[Any]) -> list[str]:
    """Produce next-step suggestions tailored to the run outcome."""
    steps: list[str] = []

    if status == "failed":
        steps.append("Fix the error shown above and re-run the crawl")
    elif status == "interrupted":
        steps.append("Re-run the command to continue from a fresh run directory")

    if stats.processed > 0:
        steps.append("Run: registrar")

    if stats.rejected > 0:
        rejection_artifacts = ctx.rejection_sink.artifacts()
        target = rejection_artifacts[0] if rejection_artifacts else "rejected.jsonl"
        steps.append(f"Review rejected records in {target}")

    if stats.failed > 0:
        steps.append("Investigate worker failures (parser bug — see warnings above)")

    return steps
