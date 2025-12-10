"""
eCUDO Crawler

High-level orchestration for crawling eCUDO organizations.
Integrates all components: API client, parsers, processors, and parallel execution.
"""

import asyncio
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from ecudo import output
from ecudo.config import Config
from ecudo.ecudo_api import EcudoClient, EcudoRecordIDIterator
from ecudo.metadata import openaire
from ecudo.orchestration import ProcessingStats, run_parallel_pipeline
from ecudo.parsers.ecudo import parse_record
from ecudo.processors import DiversityFilter, Processor, ProcessorPipeline, URLValidator
from ecudo.processors.converters import OnedataConverter
from ecudo.processors.fetchers import MetadataFetcher
from ecudo.processors.writers import JSONLWriter


class EcudoCrawler:  # pylint: disable=too-few-public-methods
    """Orchestrates crawling of an eCUDO organization."""

    def __init__(
        self,
        organization: str,
        config: Config,
        max_records: int | None = None,
    ):
        self.organization = organization
        self.config = config
        self.max_records = max_records

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

                record_id_iterator = self._build_record_iterator(client)

                pipeline = self._build_pipeline(client)
                await pipeline.open()
                stack.push_async_callback(pipeline.close)

                crawler_stats = await self._crawl(record_id_iterator, pipeline)
                pipeline_stats = pipeline.get_stats()

                self._print_summary(crawler_stats, pipeline_stats)

        except (KeyboardInterrupt, asyncio.CancelledError):
            self.interrupted = True
            output.warning("\n⚠️ Interrupted by user (Ctrl+C)")
            self._print_summary(None, None)

    async def _validate_organization(self, client: EcudoClient) -> None:
        """Ensure the requested organization exists."""
        output.info("📡 Validating organization...")
        orgs = await client.get_organizations()
        if not any(o["id"] == self.organization for o in orgs):
            output.error(f"❌ Organization '{self.organization}' not found.")
            output.error(f"   Available: {', '.join(o['id'] for o in orgs)}")
            sys.exit(1)
        output.info(f"✅ Found organization: {self.organization}")

    def _build_record_iterator(self, client: EcudoClient) -> EcudoRecordIDIterator:
        return EcudoRecordIDIterator(
            client=client,
            org_id=self.organization,
            page_size=self.config.crawler.page_size,
            max_records=self.max_records,
        )

    def _build_pipeline(self, client: EcudoClient) -> ProcessorPipeline:
        """Assemble the processing pipeline based on configuration."""
        output.info("\n📦 Building processing pipeline...")
        processors: list[Processor] = []

        output.info("   ✓ MetadataFetcher: fetch and parse JSON-LD")
        processors.append(MetadataFetcher(client, parse_record))

        if self.config.processors.url_validator.enabled:
            output.info("   ✓ URLValidator: check URL accessibility")
            processors.append(URLValidator(client))
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
        self, record_id_iterator: EcudoRecordIDIterator, pipeline: ProcessorPipeline
    ) -> ProcessingStats:
        """Execute the parallel fetcher and return run statistics."""
        output.info(f"\n🚀 Starting parallel crawl of {self.organization}...")
        if self.max_records:
            output.info(f"   Limit: {self.max_records} records")
        output.info(f"   Concurrency: {self.config.crawler.concurrency} workers")
        output.info(f"   Queue size: {self.config.crawler.queue_size}")

        stats = await run_parallel_pipeline(
            id_source=record_id_iterator,
            pipeline=pipeline,
            concurrency=self.config.crawler.concurrency,
            queue_size=self.config.crawler.queue_size,
        )
        return stats

    def _print_summary(
        self, crawler_stats: ProcessingStats | None, pipeline_stats: dict | None
    ) -> None:
        """Print final crawl summary (always shown, even on interrupt)."""
        output.always("\n" + "=" * 80)
        if self.interrupted:
            output.always("Crawl Interrupted!")
        else:
            output.always("Crawl Complete!")
        output.always("=" * 80)
        output.always(f"Raw datasets saved to:       {self.raw_output_file}")
        output.always(f"Processed datasets saved to: {self.processed_output_file}")

        if crawler_stats:
            output.always(f"\nStatistics: {crawler_stats}")

        if pipeline_stats and pipeline_stats.get("processors"):
            output.always("\nProcessor statistics:")
            for name, proc_stats in pipeline_stats["processors"].items():
                stats_str = ", ".join(f"{k}: {v}" for k, v in proc_stats.items())
                output.always(f"   {name}: {stats_str}")

        output.always("\nNext steps:")
        output.always(
            f"  1. Convert JSONL to JSON: python -m ecudo convert {self.processed_output_file}"
        )
        output.always("  2. Run dataset_registrar.py with the converted file")
        output.always("=" * 80)
