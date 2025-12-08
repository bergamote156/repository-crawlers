"""
eCUDO Crawler

High-level orchestration for crawling eCUDO organizations.
Integrates all components: API client, parsers, processors, and parallel execution.
"""

import sys
from contextlib import AsyncExitStack
from pathlib import Path

from ecudo.config import Config
from ecudo.ecudo_api import EcudoClient, EcudoRecordIDIterator
from ecudo.metadata import openaire
from ecudo.orchestration import ProcessingStats, run_parallel_pipeline
from ecudo.parsers.ecudo import parse_record
from ecudo.processors import DiversityFilter, Processor, ProcessorPipeline, URLValidator
from ecudo.processors.converters import OnedataConverter
from ecudo.processors.fetchers import MetadataFetcher
from ecudo.processors.writers import JSONLWriter, RawRecordWriter


class EcudoCrawler:
    """Orchestrates crawling of an eCUDO organization."""

    def __init__(
        self,
        organization: str,
        config: Config,
        max_records: int | None = None,
        quiet: bool = False,
    ):
        self.organization = organization
        self.config = config
        self.max_records = max_records
        self.quiet = quiet

        output_dir = Path(self.config.output.dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        self._raw_output = output_dir / f"{self.organization}_raw.jsonl"
        self._processed_output = output_dir / f"{self.organization}_processed.jsonl"

    def log(self, message: str) -> None:
        """Print message if not in quiet mode."""
        if not self.quiet:
            print(message)

    async def run(self) -> None:
        """Execute the crawl."""
        self.log("=" * 80)
        self.log(f"eCUDO Crawler - Organization: {self.organization.upper()}")
        self.log("=" * 80)

        async with AsyncExitStack() as stack:
            client = await stack.enter_async_context(
                EcudoClient(
                    base_url=self.config.crawler.base_url,
                    timeout=self.config.crawler.timeout,
                    max_retries=self.config.crawler.max_retries,
                )
            )

            await self._validate_organization(client)

            processors = self._build_pipeline_processors(client)
            pipeline: ProcessorPipeline = ProcessorPipeline(processors)
            await pipeline.open()
            stack.push_async_callback(pipeline.close)

            id_iterator = EcudoRecordIDIterator(
                client=client,
                org_id=self.organization,
                page_size=self.config.crawler.page_size,
                max_records=self.max_records,
            )

            stats, pipeline_stats = await self._run_fetcher(id_iterator, pipeline)
            self._print_summary(stats, pipeline_stats)

    async def _validate_organization(self, client: EcudoClient) -> None:
        """Ensure the requested organization exists."""
        self.log("📡 Validating organization...")
        orgs = await client.get_organizations()
        if not any(o["id"] == self.organization for o in orgs):
            print(f"❌ Organization '{self.organization}' not found.")
            print(f"   Available: {', '.join(o['id'] for o in orgs)}")
            sys.exit(1)
        self.log(f"✅ Found organization: {self.organization}")

    def _build_pipeline_processors(self, client: EcudoClient) -> list[Processor]:
        """Assemble the processing pipeline based on configuration."""
        self.log("\n📦 Building processing pipeline...")
        processors: list[Processor] = []

        self.log("   ✓ MetadataFetcher: fetch and parse JSON-LD")
        processors.append(MetadataFetcher(client, parse_record))

        if self.config.processors.url_validator.enabled:
            self.log("   ✓ URLValidator: check URL accessibility")
            processors.append(URLValidator(client))
        else:
            self.log("   ⊘ URLValidator: disabled")

        if self.config.processors.diversity_filter.enabled:
            df_cfg = self.config.processors.diversity_filter
            self.log(
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
            self.log("   ⊘ DiversityFilter: disabled")

        self.log(f"   ✓ RawRecordWriter: {self._raw_output}")
        processors.append(RawRecordWriter(self._raw_output))

        self.log("   ✓ OnedataConverter: build Onedata dataset with OpenAIRE XML")
        processors.append(OnedataConverter(openaire.generate_xml))

        self.log(f"   ✓ JSONLWriter: {self._processed_output}")
        processors.append(JSONLWriter(self._processed_output))

        return processors

    async def _run_fetcher(
        self,
        id_iterator: EcudoRecordIDIterator,
        pipeline: ProcessorPipeline,
    ) -> tuple[ProcessingStats, dict]:
        """Execute the parallel fetcher and return run statistics."""
        self.log(f"\n🚀 Starting parallel crawl of {self.organization}...")
        if self.max_records:
            self.log(f"   Limit: {self.max_records} records")
        self.log(f"   Concurrency: {self.config.crawler.concurrency} workers")
        self.log(f"   Queue size: {self.config.crawler.queue_size}")

        stats = await run_parallel_pipeline(
            id_source=id_iterator,
            pipeline=pipeline,
            concurrency=self.config.crawler.concurrency,
            queue_size=self.config.crawler.queue_size,
            verbose=not self.quiet,
        )
        pipeline_stats = pipeline.get_stats()
        return stats, pipeline_stats

    def _print_summary(self, stats: ProcessingStats, pipeline_stats: dict) -> None:
        """Print final crawl summary."""
        print("\n" + "=" * 80)
        print("Crawl Complete!")
        print("=" * 80)
        print(f"Raw datasets saved to:       {self._raw_output}")
        print(f"Processed datasets saved to: {self._processed_output}")
        print(f"\nStatistics: {stats}")

        if pipeline_stats.get("processors"):
            print("\nProcessor statistics:")
            for name, proc_stats in pipeline_stats["processors"].items():
                stats_str = ", ".join(f"{k}: {v}" for k, v in proc_stats.items())
                print(f"   {name}: {stats_str}")

        print("\nNext steps:")
        print(
            f"  1. Convert JSONL to JSON: python -m ecudo convert {self._processed_output}"
        )
        print("  2. Run dataset_registrar.py with the converted file")
        print("=" * 80)
