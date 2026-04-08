"""
Simple crawler plugin base class.

One class, one file. Subclasses:

1. declare `name`, `description`, and (optionally) `config_class`;
2. implement `setup` to open HTTP/API clients on `self` (registering
   cleanups on the provided `AsyncExitStack`);
3. implement `iterate_datasets` as an async generator over raw items;
4. implement `parse` returning `Result[OnedataDataset, failure]` or
   `None` (for silent skips).

The framework wires `before_crawl`/`after_crawl` hooks, runs
`parse` in parallel workers, and persists `processed.jsonl` and
`rejected.jsonl`.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import asyncio
from abc import abstractmethod
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from dataclasses import asdict
from pathlib import Path
from pprint import pformat
from typing import Any

from rich.panel import Panel
from rich.table import Table

from crawlers.core.onedata import OnedataDataset
from crawlers.core.plugin import CommandDef, CrawlerPlugin
from crawlers.core.result import Result
from crawlers.core.workspace import make_run_dir
from crawlers.simple.config import SimpleCrawlConfig
from crawlers.simple.runner import CrawlStats, run_parallel_crawl
from crawlers.simple.workspace import SimpleRunContext
from crawlers.ui import console


# pylint: disable=unused-argument
class SimpleCrawlerPlugin[RawT, ConfigT: SimpleCrawlConfig](CrawlerPlugin):
    """
    Batteries-included base for crawler plugins.

    Subclass and implement `iterate_datasets` + `parse`. Open resources
    in `setup` (register cleanups on the `AsyncExitStack`) so they are
    torn down even when the crawl is interrupted.

    Example:
        class MyCrawler(SimpleCrawlerPlugin[dict, MyConfig]):
            name = "myapi"
            description = "Crawl My API"
            config_class = MyConfig

            async def setup(self, ctx, stack):
                http = await stack.enter_async_context(
                    HttpClient.from_config(ctx.config),
                )
                self._api = MyApi(http)
                self._http_for_validation = (
                    None if ctx.config.no_url_validation else http
                )

            async def iterate_datasets(self, ctx):
                async for record in self._api.iter_records():
                    yield record

            async def parse(self, raw):
                return await OnedataDataset.build(
                    pid=raw["id"],
                    name=raw["title"],
                    location=raw["title"].replace("/", "-"),
                    metadata=build_metadata(raw),
                    files=extract_files(raw),
                    http=self._http_for_validation,
                )
    """

    name: str
    description: str
    config_class: type[ConfigT] = SimpleCrawlConfig  # type: ignore[assignment]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Auto-register the `crawl` command on concrete subclasses."""
        super().__init_subclass__(**kwargs)

        if isinstance(cls.__dict__.get("name"), str) and "crawl" not in cls._commands:
            config_cls = cls.__dict__.get("config_class", cls.config_class)
            cls._commands["crawl"] = CommandDef(
                name="crawl",
                help="Crawl datasets",
                method_name="run_crawl",
                config_class=config_cls,
            )

    # --- Plugin lifecycle hooks ---

    async def setup(
        self, ctx: SimpleRunContext[ConfigT], stack: AsyncExitStack
    ) -> None:
        """
        Open plugin resources (HTTP clients, sinks, credentials).

        Store them on `self` and register async context managers on
        `stack` so they are closed automatically when the crawl ends.
        """

    async def before_crawl(self, ctx: SimpleRunContext[ConfigT]) -> None:
        """Run once after `setup` and before the worker pool starts."""

    async def after_crawl(self, ctx: SimpleRunContext[ConfigT]) -> None:
        """Run once after the worker pool finishes successfully."""

    # --- Abstract: plugin body ---

    @abstractmethod
    async def iterate_datasets(
        self, ctx: SimpleRunContext[ConfigT]
    ) -> AsyncIterator[RawT]:
        """Async-iterate raw items from the upstream API."""
        raise NotImplementedError
        yield  # pragma: no cover  # makes this an async generator so subclass overrides match

    @abstractmethod
    async def parse(self, raw: RawT, /) -> Result[OnedataDataset, Any] | None:
        """
        Convert a raw item into an `OnedataDataset`.

        Returns:
            - `Ok(dataset)`: persisted to `processed.jsonl`
            - `Err(failure)`: persisted to `rejected.jsonl` (via `to_json`)
            - `None`: silently skipped (e.g. item below quality threshold)
        """
        raise NotImplementedError

    # --- Optional overrides ---

    def run_context_name(self, config: ConfigT) -> str:
        """Short identifier appended to the run directory name."""
        return "default"

    # --- Main execution ---

    async def run_crawl(self, config: ConfigT, stack: AsyncExitStack) -> None:
        """
        Execute the `crawl` command. Wired automatically by `__init_subclass__`.

        `stack` is injected by the dispatcher: cleanup of `ctx` (closing
        sinks, writing final state.json) and of the summary print is
        registered on it, so the run is finalized cleanly even when
        `setup` or `before_crawl` raises.
        """
        ctx = self._create_run_context(config)
        await ctx.open(
            config_snapshot={
                "plugin": self.name,
                "config": asdict(config),  # type: ignore[call-overload]
            }
        )

        # Mutable holder captured by the finalize callback below. Using a
        # dict (vs. nonlocal) keeps the closure trivially inspectable.
        state: dict[str, Any] = {"status": "pending", "stats": CrawlStats()}

        async def finalize() -> None:
            await ctx.close(state["status"])
            self._print_summary(state["status"], state["stats"], ctx)

        stack.push_async_callback(finalize)

        self._print_banner(ctx)

        try:
            await self.setup(ctx, stack)
            await self.before_crawl(ctx)

            stats = await run_parallel_crawl(
                source_iterator=self.iterate_datasets(ctx),
                parse_fn=self.parse,
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

    # --- Internals ---

    def _create_run_context(self, config: ConfigT) -> SimpleRunContext[ConfigT]:
        run_dir = make_run_dir(
            workspace=Path(config.output_dir),
            plugin=self.name,
            context=self.run_context_name(config),
        )
        return SimpleRunContext(run_dir=run_dir, config=config)

    # --- Display ---

    def _print_banner(self, ctx: SimpleRunContext[ConfigT]) -> None:
        title = type(self).__name__
        content = f"[header]{title}[/]"
        # pylint: disable=assignment-from-none
        subtitle = self.run_context_name(ctx.config)
        content += f"\n[muted]{subtitle}[/]"
        content += f"\n[muted]Run: {ctx.run_dir}[/]"

        console.print(Panel(content, expand=False, border_style="cyan"))
        console.newline()
        console.debug(pformat(ctx.config))

    def _print_summary(
        self, status: str, stats: CrawlStats, ctx: SimpleRunContext[ConfigT]
    ) -> None:
        # "Setup-time failure" = we never started queuing work, so the
        # stats table and output files would just be rows of zeros and
        # empty paths. Collapse the summary to the essential diagnosis.
        setup_failed = status == "failed" and stats.queued == 0

        console.newline()
        if status == "interrupted":
            console.print(
                Panel("[warning]:warning: Crawl Interrupted[/]", border_style="yellow")
            )
        elif status == "failed":
            console.print(
                Panel("[error]:cross_mark: Crawl Failed[/]", border_style="red")
            )
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


def _build_next_steps(
    status: str, stats: CrawlStats, ctx: SimpleRunContext[Any]
) -> list[str]:
    """
    Produce next-step suggestions tailored to the run outcome.

    The old hard-coded "Run: registrar" lied when the crawl failed in
    setup/before_crawl or produced zero processed records. Suggestions
    are now conditional on what actually happened.
    """
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
