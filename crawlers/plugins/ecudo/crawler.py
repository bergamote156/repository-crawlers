"""
Ecudo Crawler.

Crawler implementation for the eCUDO data repository.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import sys
from pathlib import Path
from typing import Any, AsyncIterable, cast

from crawlers.core import output
from crawlers.core.abc.api import ApiClient
from crawlers.core.abc.processor import Processor
from crawlers.core.crawler import BaseCrawler
from crawlers.core.metadata.openaire import OpenAIREBuilder
from crawlers.core.onedata import OnedataDataset
from crawlers.core.processors.converters import OnedataConverter
from crawlers.core.processors.fetchers import DatasetFetcher
from crawlers.core.processors.filters import DiversityFilter
from crawlers.core.processors.pipeline import ProcessorPipeline
from crawlers.core.processors.validators import URLValidator
from crawlers.core.processors.writers import JSONLWriter
from crawlers.plugins.ecudo.api import EcudoClient, EcudoIteratorOpts
from crawlers.plugins.ecudo.config import EcudoCrawlConfig
from crawlers.plugins.ecudo.models import EcudoDataset
from crawlers.plugins.ecudo.parser import EcudoParser


class EcudoCrawler(BaseCrawler[EcudoCrawlConfig]):
    """
    Crawler implementation for eCUDO.

    Fetches datasets from eCUDO API, processes them through a pipeline
    (validation, filtering, conversion), and writes output to JSONL files.
    """

    def __init__(self, config: EcudoCrawlConfig):
        """Initialize crawler with output file paths."""
        super().__init__(config)

        # Setup output directory and file paths
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        org = config.organization
        self.raw_output_file = output_dir / f"{org}_raw.jsonl"
        self.processed_output_file = output_dir / f"{org}_processed.jsonl"

    def create_client(self) -> EcudoClient:
        """Create eCUDO API client."""
        return EcudoClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            max_retries=self.config.max_retries,
        )

    def create_iterator(self, client: EcudoClient) -> AsyncIterable[Any]:
        """Create iterator over eCUDO dataset IDs."""
        ecudo_client = client

        opts = EcudoIteratorOpts(
            org_id=self.config.organization,
            page_size=self.config.page_size,
            max_datasets=self.config.max_records,
        )

        return ecudo_client.iterate_datasets(opts)

    def build_pipeline(self, client: EcudoClient) -> ProcessorPipeline:
        """
        Build the processing pipeline.

        Pipeline stages:
        1. Fetcher: ID -> EcudoDataset
        2. URLValidator (optional): validate distribution URLs
        3. DiversityFilter (optional): filter similar datasets
        4. RawWriter: write raw EcudoDataset to JSONL
        5. Converter: EcudoDataset -> OnedataDataset
        6. ProcessedWriter: write OnedataDataset to JSONL
        """
        ecudo_client = cast(EcudoClient, client)

        output.info("\n📦 Building processing pipeline...")
        processors: list[Processor] = []

        # 1. Fetcher: ID -> EcudoDataset
        output.info("   ✓ DatasetFetcher: fetch and parse JSON-LD")
        fetcher = DatasetFetcher[dict, EcudoDataset](
            fetch_fn=ecudo_client.get_dataset_metadata,
            parser=EcudoParser(),
        )
        processors.append(fetcher)

        # 2. URL Validator (optional)
        if self.config.get_url_validator_enabled():
            log_path = self.config.processors.url_validator.invalid_url_log
            log_note = f" (log: {log_path})" if log_path else ""
            output.info(f"   ✓ URLValidator: check URL accessibility{log_note}")
            processors.append(
                URLValidator[EcudoDataset](
                    validate_fn=ecudo_client.validate_url,
                    invalid_url_log=(Path(log_path) if log_path else None),
                )
            )
        else:
            output.info("   ⊘ URLValidator: disabled")

        # 3. Diversity Filter (optional)
        if self.config.get_diversity_filter_enabled():
            df_cfg = self.config.processors.diversity_filter
            output.info(
                f"   ✓ DiversityFilter: max {df_cfg.max_similar} similar "
                f"({df_cfg.similarity_threshold:.0%} threshold)"
            )
            processors.append(
                DiversityFilter[EcudoDataset](
                    max_similar=df_cfg.max_similar,
                    similarity_threshold=df_cfg.similarity_threshold,
                )
            )
        else:
            output.info("   ⊘ DiversityFilter: disabled")

        # 4. Raw output writer (before conversion)
        output.info(f"   ✓ RawRecordWriter: {self.raw_output_file}")
        processors.append(JSONLWriter[EcudoDataset](output_path=self.raw_output_file))

        # 5. Converter: EcudoDataset -> OnedataDataset
        output.info("   ✓ OnedataConverter: build Onedata dataset with OpenAIRE XML")
        metadata_builder = OpenAIREBuilder()
        processors.append(
            OnedataConverter[EcudoDataset](metadata_builder=metadata_builder)
        )

        # 6. Processed output writer (after conversion)
        output.info(f"   ✓ ProcessedWriter: {self.processed_output_file}")
        processors.append(
            JSONLWriter[OnedataDataset](output_path=self.processed_output_file)
        )

        return ProcessorPipeline(processors)

    async def before_crawl(self, client: ApiClient) -> None:
        """Validate that the requested organization exists."""
        ecudo_client = cast(EcudoClient, client)

        output.info("📡 Validating organization...")
        orgs = await ecudo_client.get_organizations()

        if not any(o["id"] == self.config.organization for o in orgs):
            output.error(f"Organization '{self.config.organization}' not found.")
            output.error(f"   Available: {', '.join(o['id'] for o in orgs)}")
            sys.exit(1)

        output.info(f"✅ Found organization: {self.config.organization}")

        # Log crawl parameters
        output.info(f"\n🚀 Starting parallel crawl of {self.config.organization}...")
        if self.config.max_records:
            output.info(f"   Limit: {self.config.max_records} datasets")
        output.info(f"   Concurrency: {self.config.concurrency} workers")
        output.info(f"   Queue size: {self.config.queue_size}")

    def _print_banner(self) -> None:
        """Print eCUDO crawler banner."""
        output.info("=" * 80)
        output.info(f"eCUDO Crawler - Organization: {self.config.organization.upper()}")
        output.info("=" * 80)

    def _print_summary(self) -> None:
        """Print detailed crawl summary."""
        super()._print_summary()

        output.always(f"Raw datasets saved to:       {self.raw_output_file}")
        output.always(f"Processed datasets saved to: {self.processed_output_file}")

        output.always("\nNext steps:")
        output.always(
            f"  1. Run: python -m registrar register {self.processed_output_file}"
        )
        output.always("=" * 80)
