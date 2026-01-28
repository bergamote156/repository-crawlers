"""Base Crawler."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import asyncio
from abc import ABC, abstractmethod
from pprint import pformat
from typing import Any, AsyncIterable

from crawlers.core import output
from crawlers.core.abc.api import ApiClient
from crawlers.core.config import BaseCrawlConfig
from crawlers.core.orchestration.parallel import CrawlStats, run_parallel_pipeline
from crawlers.core.processors.pipeline import ProcessorPipeline


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
                    )
                finally:
                    await self._pipeline.close()

                await self.after_crawl()

        except (KeyboardInterrupt, asyncio.CancelledError):
            self.interrupted = True
            output.warning("\nInterrupted by user (Ctrl+C)")

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

    def _print_banner(self) -> None:
        """
        Print banner at crawl start.

        Override in subclass for custom banner.
        """
        output.info(f"Starting crawler: {self.__class__.__name__}")
        output.debug(f"{pformat(self.config)}")

    def _print_pipeline(self) -> None:
        """
        Print pipeline description after building.

        Uses pipeline.format_description() to show all processors.
        """
        if self._pipeline:
            output.info("\n📦 Processing pipeline:")
            output.info(self._pipeline.format_description())

    def _print_summary(self) -> None:
        """
        Print summary at crawl end (always called, even on interrupt).

        Prints processor statistics, overall stats, and output artifacts.
        Override in subclass for custom summary additions.
        """
        output.always("\n" + "=" * 80)
        if self.interrupted:
            output.always("Crawl Interrupted!")
        else:
            output.always("Crawl Complete!")
        output.always("=" * 80)

        # Print processor statistics
        if self._pipeline:
            output.always("\nProcessor Statistics:")
            for name, stats in self._pipeline.get_processor_stats():
                output.always(f"  {name}: {stats}")

        # Print overall crawl stats
        if self.stats:
            output.always(f"\nOverall: {self.stats}")

        # Print output artifacts collected from pipeline
        if self._pipeline:
            artifacts = self._pipeline.get_artifacts()
            if artifacts:
                output.always("\nOutput files:")
                for path in artifacts:
                    output.always(f"  {path}")

        output.always("\nNext steps:")
        output.always("  1. Run: registrar")
        output.always("=" * 80)
