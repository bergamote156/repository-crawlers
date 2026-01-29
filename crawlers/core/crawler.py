"""Base Crawler."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import asyncio
from abc import ABC, abstractmethod
from pprint import pformat
from typing import Any, AsyncIterable

from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from crawlers.core.abc.api import ApiClient
from crawlers.core.config import BaseCrawlConfig
from crawlers.core.orchestration.parallel import CrawlStats, run_parallel_pipeline
from crawlers.core.processors.pipeline import ProcessorPipeline
from crawlers.core.ui import console


class BaseCrawler[ConfigT: BaseCrawlConfig](ABC):
    """
    Abstract base class for crawlers.

    Orchestrates the crawling process:
    1. Prints banner
    2. Initializes API client
    3. Runs pre-crawl hooks (validation)
    4. Builds and opens processing pipeline
    5. Executes parallel crawl loop
    6. Runs post-crawl hooks
    7. Prints summary (always, even on interrupt)
    """

    def __init__(self, config: ConfigT):
        """
        Initialize crawler.

        Args:
            config: Specific configuration for this crawler
        """
        self.config = config
        self.stats: CrawlStats | None = None
        self.interrupted = False
        self._pipeline: ProcessorPipeline | None = None

    async def run(self) -> None:
        """Execute the main crawl loop with interrupt handling."""
        self._print_banner()

        try:
            async with self.create_client() as client:
                await self.before_crawl(client)

                self._pipeline = self.build_pipeline(client)
                self._print_pipeline()

                await self._pipeline.open()

                try:
                    iterator = self.create_iterator(client)
                    self.stats = await run_parallel_pipeline(
                        source_iterator=iterator,
                        pipeline=self._pipeline,
                        concurrency=self.config.concurrency,
                        queue_size=self.config.queue_size,
                        max_items=self.get_max_items(),
                    )
                finally:
                    await self._pipeline.close()

                await self.after_crawl()

        except (KeyboardInterrupt, asyncio.CancelledError):
            self.interrupted = True
            console.warning("Interrupted by user (Ctrl+C)")

        finally:
            self._print_summary()

    # --- Abstract Methods (Must be implemented by Plugin) ---

    @abstractmethod
    def create_client(self) -> ApiClient:
        """
        Create the API client.

        Returns:
            Configured ApiClient instance
        """
        raise NotImplementedError

    @abstractmethod
    def build_pipeline(self, client: ApiClient) -> ProcessorPipeline:
        """
        Build the processing pipeline.

        Args:
            client: Initialized API client

        Returns:
            ProcessorPipeline ready for execution
        """
        raise NotImplementedError

    @abstractmethod
    def create_iterator(self, client: ApiClient) -> AsyncIterable[Any]:
        """
        Create iterator over items to process (e.g. dataset IDs).

        Args:
            client: Initialized API client

        Returns:
            Async iterable yielding items for the pipeline
        """
        raise NotImplementedError

    # --- Optional Hooks ---

    async def before_crawl(self, client: ApiClient) -> None:
        """
        Hook executed before processing starts.

        Use for validation (e.g. check organization exists) or setup.
        """

    async def after_crawl(self) -> None:
        """
        Hook executed after processing ends successfully.

        Use for custom post-processing. Note: _print_summary() is called
        separately and always runs (even on interrupt).
        """

    def get_max_items(self) -> int | None:
        """
        Get maximum items to process.

        Override in subclass to return max_items/max_records from config.
        Used for progress tracking - returns None by default (unknown total).

        Returns:
            Maximum items count or None if unknown
        """
        return None

    def _print_banner(self) -> None:
        """
        Print banner at crawl start.

        Override in subclass for custom banner.
        """
        title = self.__class__.__name__
        subtitle = self._get_banner_subtitle()

        content = f"[header]{title}[/]"
        if subtitle:
            content += f"\n[muted]{subtitle}[/]"

        console.print(Panel(content, expand=False, border_style="cyan"))
        console.newline()

        console.debug(pformat(self.config))

    def _get_banner_subtitle(self) -> str | None:
        """
        Get subtitle for banner.

        Override in subclass to provide context (e.g. collection name).
        """
        return None

    def _print_pipeline(self) -> None:
        """
        Print pipeline description after building.

        Uses pipeline.get_processor_info() to show all processors as tree.
        """
        if self._pipeline:
            tree = Tree("[highlight]Processing Pipeline[/]")

            processors = self._pipeline.get_processor_info()
            for i, (name, desc, enabled) in enumerate(processors, 1):
                if enabled:
                    style = "processor.enabled"
                    icon = ":white_check_mark:"
                else:
                    style = "processor.disabled"
                    icon = ":prohibited:"

                tree.add(f"[{style}]{i}. {icon} {name}[/]: {desc}")

            console.print(tree)
            console.newline()

    def _print_summary(self) -> None:
        """
        Print summary at crawl end (always called, even on interrupt).

        Prints processor statistics, overall stats, and output artifacts.
        Override in subclass for custom summary additions.
        """
        processor_stats: list[tuple[str, Any]] = []
        artifacts = []

        if self._pipeline:
            processor_stats = self._pipeline.get_processor_stats()
            artifacts = self._pipeline.get_artifacts()

        overall_stats = self.stats or CrawlStats()

        # Status header panel
        console.newline()
        if self.interrupted:
            console.print(
                Panel("[warning]:warning: Crawl Interrupted[/]", border_style="yellow")
            )
        else:
            console.print(
                Panel(
                    "[success]:white_check_mark: Crawl Complete[/]",
                    border_style="green",
                )
            )

        # Processor statistics table
        console.section("Processor Statistics")
        stats_table = Table(show_header=True, header_style="bold")
        stats_table.add_column("Processor", style="cyan")
        stats_table.add_column("Result", justify="right")

        for name, stats in processor_stats:
            stats_table.add_row(name, str(stats))

        console.print(stats_table)

        # Overall stats
        console.section("Overall")
        console.print(f"  {overall_stats}")

        # Output files
        if artifacts:
            console.section("Output Files")
            for path in artifacts:
                console.print(f"  [muted]>[/] {path}")

        # Next steps
        next_steps = ["Run: registrar"]

        console.section("Next Steps")
        for i, step in enumerate(next_steps, 1):
            console.print(f"  {i}. {step}")
