"""
Default Crawler Plugin.

One-class plugin that combines CrawlerPlugin + pipeline orchestration.
Subclass and implement prepare_crawl() to return a CrawlSpec.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import asyncio
from abc import abstractmethod
from dataclasses import asdict
from pathlib import Path
from pprint import pformat
from typing import Any

from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from crawlers.core.orchestration import CrawlStats, run_parallel_pipeline
from crawlers.core.plugin import CrawlerPlugin
from crawlers.core.processor import Processor
from crawlers.core.workspace import RunContext, make_run_dir
from crawlers.default.config import DefaultCrawlConfig
from crawlers.default.crawl_spec import DefaultCrawlSpec
from crawlers.default.workspace import DefaultRunContext
from crawlers.processors import (
    DatasetResolver,
    OnedataConverter,
    ProcessorPipeline,
    Tap,
    URLValidator,
)
from crawlers.processors.parsers import ParserProcessor
from crawlers.ui import console


class DefaultCrawlerPlugin(CrawlerPlugin):
    """
    Batteries-included base class for crawler plugins.

    Subclass and implement prepare_crawl() to describe the crawl.
    The framework handles client lifecycle, pipeline construction,
    parallel execution, state persistence, and display.

    Optional hooks:
        before_crawl(spec): called after client session is opened
        after_crawl(): called after successful crawl completion

    Config:
        Set config_class to a DefaultCrawlConfig subclass.

    Example:
        class MyCrawler(DefaultCrawlerPlugin):
            name = "myapi"
            description = "Crawl My API"
            config_class = MyConfig

            def prepare_crawl(self, config: MyConfig) -> CrawlSpec:
                client = MyApiClient(base_url=config.base_url)
                return CrawlSpec(
                    client=client,
                    iterator_opts=MyOpts(page_size=config.page_size),
                    parser=MyParser(),
                    metadata_builder=MyMetadataBuilder(),
                    run_context_name=config.name,
                    max_items=config.max_records,
                )
    """

    name: str
    description: str
    config_class: type[DefaultCrawlConfig] = DefaultCrawlConfig

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Auto-register 'crawl' command on concrete subclasses."""
        super().__init_subclass__(**kwargs)

        if isinstance(cls.__dict__.get("name"), str) and "crawl" not in cls._commands:
            # pylint: disable=import-outside-toplevel
            from crawlers.core.plugin import CommandDef

            config_cls = cls.__dict__.get("config_class", cls.config_class)
            cls._commands["crawl"] = CommandDef(
                name="crawl",
                help="Crawl datasets",
                method_name="run_crawl",
                config_class=config_cls,
            )

    @abstractmethod
    def prepare_crawl(self, config: DefaultCrawlConfig) -> DefaultCrawlSpec:
        """
        Describe the crawl run.

        Called once before the client session is opened. Return a CrawlSpec
        with all components needed to execute the crawl.

        Args:
            config: Validated CLI/YAML configuration

        Returns:
            CrawlSpec with client, iterator opts, parser, and metadata builder
        """
        raise NotImplementedError

    async def before_crawl(self, ctx: DefaultRunContext) -> None:
        """
        Hook called after client session is opened, before crawling starts.

        Override for validation (e.g. check organization exists, verify
        credentials). spec.client is open and ready for requests.
        """

    async def after_crawl(self, ctx: DefaultRunContext) -> None:
        """Hook called after successful crawl completion."""

    # --- Main execution ---

    async def run_crawl(self, config: DefaultCrawlConfig) -> None:
        """Execute the crawl command. Wired automatically by __init_subclass__."""
        spec = self.prepare_crawl(config)

        ctx = self._create_run_context(config, spec)
        await ctx.open(
            config_snapshot={
                "plugin": self.name,
                "config": asdict(config),  # type: ignore[call-overload]
            }
        )

        self._print_banner(ctx)

        status = "pending"
        pipeline: ProcessorPipeline | None = None
        stats: CrawlStats | None = None

        try:
            async with spec.client:
                await self.before_crawl(ctx)

                pipeline = self.build_pipeline(ctx)
                self._print_pipeline(pipeline)
                await pipeline.open()

                try:
                    iterator = spec.client.iterate_datasets(spec.iterator_opts)

                    stats = await run_parallel_pipeline(
                        source_iterator=iterator,
                        pipeline=pipeline,
                        concurrency=config.concurrency,
                        queue_size=config.queue_size,
                        max_items=config.max_records,
                        state_callback=lambda s: ctx.save_stats(asdict(s)),
                    )
                    await ctx.save_stats(asdict(stats))
                finally:
                    await pipeline.close()

                await self.after_crawl(ctx)
                status = "completed"

        except (KeyboardInterrupt, asyncio.CancelledError):
            status = "interrupted"
            console.warning("Interrupted by user (Ctrl+C)")

        except Exception:
            status = "failed"
            raise

        finally:
            await ctx.close(status)
            self._print_summary(status, pipeline, stats, ctx)

    def build_pipeline(self, ctx: DefaultRunContext) -> ProcessorPipeline:
        """Build the default processor pipeline.

        If ``resolve_fn`` is set in the crawl spec, the pipeline starts with
        a DatasetResolver (resolve + parse). Otherwise it starts with a
        plain ParserProcessor (parse only).
        """
        spec = ctx.crawl_spec

        if spec.resolve_fn:
            first_step: Processor = DatasetResolver(
                resolve_fn=spec.resolve_fn,
                parser=spec.parser,
            )
        else:
            first_step = ParserProcessor(parser=spec.parser)

        processors: list[Processor] = [
            first_step,
            URLValidator(
                validate_fn=spec.client.validate_url,
                enabled=not ctx.config.no_url_validation,
            ),
            Tap(ctx.raw_sink, transform=lambda d: d.to_json()),
            OnedataConverter(metadata_builder=spec.metadata_builder),
            Tap(ctx.processed_sink, transform=lambda d: d.to_json()),
        ]
        return ProcessorPipeline(
            processors=processors,
            rejection_sink=ctx.rejection_sink,
        )

    # --- Internals ---

    def _create_run_context(
        self, config: DefaultCrawlConfig, spec: DefaultCrawlSpec
    ) -> DefaultRunContext:
        run_dir = make_run_dir(
            workspace=Path(config.output_dir),
            plugin=self.name,
            context=spec.run_context_name,
        )
        return DefaultRunContext(run_dir=run_dir, config=config, spec=spec)

    # --- Display ---

    def _print_banner(self, ctx: DefaultRunContext) -> None:
        title = type(self).__name__
        content = f"[header]{title}[/]"
        if ctx.crawl_spec.banner_subtitle:
            content += f"\n[muted]{ctx.crawl_spec.banner_subtitle}[/]"
        content += f"\n[muted]Run: {ctx.run_dir}[/]"

        console.print(Panel(content, expand=False, border_style="cyan"))
        console.newline()
        console.debug(pformat(ctx.config))

    def _print_pipeline(self, pipeline: ProcessorPipeline) -> None:
        tree = Tree("[highlight]Processing Pipeline[/]")
        for i, (name, desc, enabled) in enumerate(pipeline.get_processor_info(), 1):
            style = "processor.enabled" if enabled else "processor.disabled"
            icon = ":white_check_mark:" if enabled else ":prohibited:"
            tree.add(f"[{style}]{i}. {icon} {name}[/]: {desc}")
        console.print(tree)
        console.newline()

    def _print_summary(
        self,
        status: str,
        pipeline: ProcessorPipeline | None,
        stats: CrawlStats | None,
        ctx: RunContext,
    ) -> None:
        processor_stats: list[tuple[str, Any]] = []
        artifacts = []
        if pipeline:
            processor_stats = pipeline.get_processor_stats()
            artifacts = pipeline.get_artifacts()

        overall = stats or CrawlStats()

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

        console.section("Processor Statistics")
        stats_table = Table(show_header=True, header_style="bold")
        stats_table.add_column("Processor", style="cyan")
        stats_table.add_column("Result", justify="right")
        for name, s in processor_stats:
            stats_table.add_row(name, str(s))
        console.print(stats_table)

        console.section("Overall")
        console.print(f"  {overall}")

        if artifacts:
            console.section("Output Files")
            for path in artifacts:
                console.print(f"  [muted]>[/] {path}")

        console.section("Run Directory")
        console.print(f"  {ctx.run_dir}")

        next_steps = ["Run: registrar"]
        if status == "interrupted":
            next_steps.insert(
                0,
                f"Resume: crawlers {self.name} crawl --resume {ctx.run_dir}",
            )
        console.section("Next Steps")
        for i, step in enumerate(next_steps, 1):
            console.print(f"  {i}. {step}")
