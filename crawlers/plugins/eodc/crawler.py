"""
EODC Crawler.

Crawler implementation for EODC STAC API (Earth Observation Data Centre).
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from pathlib import Path
from typing import Any, AsyncIterable, cast

from crawlers.core.abc.api import ApiClient
from crawlers.core.crawler import BaseCrawler
from crawlers.core.processors.converters import OnedataConverter
from crawlers.core.processors.parsers import ParserProcessor
from crawlers.core.processors.pipeline import ProcessorPipeline
from crawlers.core.processors.validators import URLValidator
from crawlers.core.processors.writers import JSONLWriter
from crawlers.plugins.eodc.api import EODCClient, EODCSearchOpts
from crawlers.plugins.eodc.config import EODCCrawlConfig
from crawlers.plugins.eodc.metadata import EODCDataCiteBuilder
from crawlers.plugins.eodc.models import EODCDataset
from crawlers.plugins.eodc.parser import EODCParser


class EODCCrawler(BaseCrawler[EODCCrawlConfig]):
    """
    Crawler implementation for EODC STAC API.

    Fetches STAC items from EODC, processes them through a pipeline
    (parsing, validation, conversion), and writes output to JSONL files.
    """

    def __init__(self, config: EODCCrawlConfig):
        """Initialize crawler with output file paths."""
        super().__init__(config)

        # Setup output directory and file paths
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Use first collection name for output files
        collections = config.get_collections_list()
        prefix = collections[0] if collections else "eodc"

        self._raw_output_path = output_dir / f"{prefix}_raw.jsonl"
        self._processed_output_path = output_dir / f"{prefix}_processed.jsonl"

    def create_client(self) -> EODCClient:
        """Create EODC STAC API client."""
        return EODCClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            max_retries=self.config.max_retries,
        )

    def create_iterator(self, client: ApiClient) -> AsyncIterable[Any]:
        """Create iterator over STAC items."""
        eodc_client = cast(EODCClient, client)

        opts = EODCSearchOpts(
            collections=self.config.get_collections_list(),
            intersects=self.config.intersects,
            datetime=self.config.datetime_range,
            limit=self.config.page_size,
            max_items=self.config.max_records,
        )

        return eodc_client.iterate_datasets(opts)

    def build_pipeline(self, client: ApiClient) -> ProcessorPipeline:
        """
        Build the processing pipeline declaratively.

        Pipeline stages:
        1. Parser: dict (STAC Item) -> EODCDataset
        2. URLValidator (optional): validate asset URLs
        3. RawWriter: write raw EODCDataset to JSONL
        4. Converter: EODCDataset -> OnedataDataset
        5. ProcessedWriter: write OnedataDataset to JSONL
        """
        eodc_client = cast(EODCClient, client)
        cfg = self.config
        url_cfg = cfg.processors.url_validator

        return ProcessorPipeline(
            [
                # 1. Parser: dict -> EODCDataset
                ParserProcessor[dict, EODCDataset](
                    parser=EODCParser(),
                ),
                # 2. URL Validator (optional)
                URLValidator[EODCDataset](  # type: ignore[type-var]
                    validate_fn=eodc_client.validate_url,
                    invalid_url_log=(
                        Path(url_cfg.invalid_url_log)
                        if url_cfg.invalid_url_log
                        else None
                    ),
                    enabled=cfg.get_url_validator_enabled(),
                ),
                # 3. Raw output writer
                JSONLWriter[EODCDataset](output_path=self._raw_output_path),
                # 4. Converter: EODCDataset -> OnedataDataset
                OnedataConverter[EODCDataset](  # type: ignore[type-var]
                    metadata_builder=EODCDataCiteBuilder(),  # type: ignore[arg-type]
                ),
                # 5. Processed output writer
                JSONLWriter(output_path=self._processed_output_path),
            ]
        )
