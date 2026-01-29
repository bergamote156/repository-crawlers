"""
Ecudo Crawler.

Crawler implementation for the eCUDO data repository.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import sys
from pathlib import Path
from typing import Any, AsyncIterable, cast

from crawlers.core.abc.api import ApiClient
from crawlers.core.crawler import BaseCrawler
from crawlers.core.ui import console
from crawlers.core.metadata.openaire import OpenAIREBuilder
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
        self._raw_output_path = output_dir / f"{org}_raw.jsonl"
        self._processed_output_path = output_dir / f"{org}_processed.jsonl"

    def create_client(self) -> EcudoClient:
        """Create eCUDO API client."""
        return EcudoClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            max_retries=self.config.max_retries,
        )

    def create_iterator(self, client: ApiClient) -> AsyncIterable[Any]:
        """Create iterator over eCUDO dataset IDs."""
        ecudo_client = cast(EcudoClient, client)

        opts = EcudoIteratorOpts(
            org_id=self.config.organization,
            page_size=self.config.page_size,
            max_datasets=self.config.max_records,
        )

        return ecudo_client.iterate_datasets(opts)

    def build_pipeline(self, client: ApiClient) -> ProcessorPipeline:
        """
        Build the processing pipeline declaratively.

        Pipeline stages:
        1. Fetcher: ID -> EcudoDataset
        2. URLValidator (optional): validate distribution URLs
        3. DiversityFilter (optional): filter similar datasets
        4. RawWriter: write raw EcudoDataset to JSONL
        5. Converter: EcudoDataset -> OnedataDataset
        6. ProcessedWriter: write OnedataDataset to JSONL
        """
        ecudo_client = cast(EcudoClient, client)
        cfg = self.config
        url_cfg = cfg.processors.url_validator
        df_cfg = cfg.processors.diversity_filter

        # TODO ignore[type-var]  # pylint: disable=fixme
        return ProcessorPipeline(
            [
                # 1. Fetcher: ID -> EcudoDataset
                DatasetFetcher[dict, EcudoDataset](
                    fetch_fn=ecudo_client.get_dataset_metadata,
                    parser=EcudoParser(),
                ),
                # 2. URL Validator (optional)
                URLValidator[EcudoDataset](  # type: ignore[type-var]
                    validate_fn=ecudo_client.validate_url,
                    invalid_url_log=(
                        Path(url_cfg.invalid_url_log)
                        if url_cfg.invalid_url_log
                        else None
                    ),
                    enabled=cfg.get_url_validator_enabled(),
                ),
                # 3. Diversity Filter (optional)
                DiversityFilter[EcudoDataset](
                    max_similar=df_cfg.max_similar,
                    similarity_threshold=df_cfg.similarity_threshold,
                    enabled=cfg.get_diversity_filter_enabled(),
                ),
                # 4. Raw output writer
                JSONLWriter[EcudoDataset](output_path=self._raw_output_path),
                # 5. Converter: EcudoDataset -> OnedataDataset
                OnedataConverter[EcudoDataset](  # type: ignore[type-var]
                    metadata_builder=OpenAIREBuilder(),  # type: ignore[arg-type]
                ),
                # 6. Processed output writer
                JSONLWriter(output_path=self._processed_output_path),
            ]
        )

    def get_max_items(self) -> int | None:
        """Return max_records from config for progress tracking."""
        return self.config.max_records

    def _get_banner_subtitle(self) -> str | None:
        """Return organization name as banner subtitle."""
        return f"Organization: {self.config.organization}"

    async def before_crawl(self, client: ApiClient) -> None:
        """Validate that the requested organization exists."""
        ecudo_client = cast(EcudoClient, client)

        with console.status("Validating organization..."):
            orgs = await ecudo_client.get_organizations()

        if not any(o["id"] == self.config.organization for o in orgs):
            console.error(f"Organization '{self.config.organization}' not found.")
            console.error(f"Available: {', '.join(o['id'] for o in orgs)}")
            sys.exit(1)

        console.success(f"Found organization: {self.config.organization}")
