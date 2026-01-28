"""
eCUDO Crawler

High-level orchestration for crawling eCUDO organizations.
Integrates all components: API client, parsers, processors, and parallel execution.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import asyncio
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from ecudo import output
from ecudo.config import Config
from ecudo.ecudo_api import EcudoClient, EcudoDatasetIDIterator
from ecudo.metadata import openaire
from ecudo.orchestration import run_parallel_pipeline
from ecudo.parsers.ecudo import parse_record
from ecudo.processors import DiversityFilter, Processor, ProcessorPipeline, URLValidator
from ecudo.processors.converters import OnedataConverter
from ecudo.processors.fetchers import DatasetFetcher
from ecudo.processors.writers import JSONLWriter


class EcudoCrawler:  # pylint: disable=too-few-public-methods
    """Orchestrates crawling of an eCUDO organization."""

    def __init__(
        self,
        organization: str,
        config: Config,
        max_datasets: int | None = None,
    ):
        self.organization = organization
        self.config = config
        self.max_datasets = max_datasets

        output_dir = Path(config.output.dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        self.raw_output_file = output_dir / f"{self.organization}_raw.jsonl"
        self.processed_output_file = output_dir / f"{self.organization}_processed.jsonl"

        self.interrupted = False

    async def run(self) -> None:
        """Execute the crawl."""
        output.info("=" * 80)
        output.info(f"eCUDO Crawler - Organization: {self.organization.upper()}")
        output.info("=" * 80)

        try:
            async with AsyncExitStack() as stack:
                client = await stack.enter_async_context(
                    EcudoClient(
                        base_url=self.config.crawler.base_url,
                        timeout=self.config.crawler.timeout,
                        max_retries=self.config.crawler.max_retries,
                    )
                )

                await self._validate_organization(client)

                dataset_id_iterator = self._build_dataset_iterator(client)

                pipeline = self._build_pipeline(client)
                await pipeline.open()
                stack.push_async_callback(pipeline.close)

                await self._crawl(dataset_id_iterator, pipeline)

                self._print_summary()

        except (KeyboardInterrupt, asyncio.CancelledError):
            self.interrupted = True
            output.warning("\nInterrupted by user (Ctrl+C)")
            self._print_summary()

    async def _validate_organization(self, client: EcudoClient) -> None:
        """Ensure the requested organization exists."""
        output.info("📡 Validating organization...")
        orgs = await client.get_organizations()
        if not any(o["id"] == self.organization for o in orgs):
            output.error(f"Organization '{self.organization}' not found.")
            output.error(f"   Available: {', '.join(o['id'] for o in orgs)}")
            sys.exit(1)
        output.info(f"✅ Found organization: {self.organization}")

    def _build_dataset_iterator(self, client: EcudoClient) -> EcudoDatasetIDIterator:
        return EcudoDatasetIDIterator(
            client=client,
            org_id=self.organization,
            page_size=self.config.crawler.page_size,
            max_datasets=self.max_datasets,
        )

    def _build_pipeline(self, client: EcudoClient) -> ProcessorPipeline:
        """Assemble the processing pipeline based on configuration."""
        output.info("\n📦 Building processing pipeline...")
        processors: list[Processor] = []

        output.info("   ✓ MetadataFetcher: fetch and parse JSON-LD")
        processors.append(DatasetFetcher(client, parse_record))

        if self.config.processors.url_validator.enabled:
            log_path = self.config.processors.url_validator.invalid_url_log
            log_note = f" (log: {log_path})" if log_path else ""
            output.info(f"   ✓ URLValidator: check URL accessibility{log_note}")
            processors.append(URLValidator(client, invalid_url_log=log_path))
        else:
            output.info("   ⊘ URLValidator: disabled")

        if self.config.processors.diversity_filter.enabled:
            df_cfg = self.config.processors.diversity_filter
            output.info(
                f"   ✓ DiversityFilter: max {df_cfg.max_similar} similar "
                f"({df_cfg.similarity_threshold:.0%} threshold)"
            )
            processors.append(
                DiversityFilter(
                    max_similar=df_cfg.max_similar,
                    similarity_threshold=df_cfg.similarity_threshold,
                )
            )
        else:
            output.info("   ⊘ DiversityFilter: disabled")

        output.info(f"   ✓ RawRecordWriter: {self.raw_output_file}")
        processors.append(JSONLWriter(self.raw_output_file))

        output.info("   ✓ OnedataConverter: build Onedata dataset with OpenAIRE XML")
        processors.append(OnedataConverter(openaire.generate_xml))

        output.info(f"   ✓ JSONLWriter: {self.processed_output_file}")
        processors.append(JSONLWriter(self.processed_output_file))

        return ProcessorPipeline(processors)

    async def _crawl(
        self, dataset_id_iterator: EcudoDatasetIDIterator, pipeline: ProcessorPipeline
    ) -> None:
        """Execute the parallel fetcher and return run statistics."""
        output.info(f"\n🚀 Starting parallel crawl of {self.organization}...")
        if self.max_datasets:
            output.info(f"   Limit: {self.max_datasets} datasets")
        output.info(f"   Concurrency: {self.config.crawler.concurrency} workers")
        output.info(f"   Queue size: {self.config.crawler.queue_size}")

        await run_parallel_pipeline(
            dataset_id_source=dataset_id_iterator,
            dataset_pipeline=pipeline,
            concurrency=self.config.crawler.concurrency,
            queue_size=self.config.crawler.queue_size,
        )

    def _print_summary(self) -> None:
        """Print final crawl summary (always shown, even on interrupt)."""
        output.always("\n" + "=" * 80)
        if self.interrupted:
            output.always("Crawl Interrupted!")
        else:
            output.always("Crawl Complete!")
        output.always("=" * 80)
        output.always(f"Raw datasets saved to:       {self.raw_output_file}")
        output.always(f"Processed datasets saved to: {self.processed_output_file}")

        output.always("\nNext steps:")
        output.always("  1. Run python -m registrar register with the converted file")
        output.always("=" * 80)
