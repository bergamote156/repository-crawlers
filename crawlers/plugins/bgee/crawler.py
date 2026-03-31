"""Bgee Crawler - orchestrates schema.org JSON-LD harvesting."""

__author__ = "Vincent Emonet"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import json
from pathlib import Path
from typing import Any, AsyncIterable, cast
from xml.dom import minidom

from crawlers.core.abc.api import ApiClient
from crawlers.core.crawler import BaseCrawler
from crawlers.core.processors.converters import OnedataConverter
from crawlers.core.processors.parsers import ParserProcessor
from crawlers.core.processors.pipeline import ProcessorPipeline
from crawlers.core.processors.writers import JSONLWriter
from crawlers.core.ui import console
from crawlers.plugins.bgee.api import BgeeClient, BgeeIteratorOpts
from crawlers.plugins.bgee.config import BgeeCrawlConfig
from crawlers.plugins.bgee.metadata import BgeeDataCiteBuilder
from crawlers.plugins.bgee.parser import BgeeParser


class BgeeCrawler(BaseCrawler[BgeeCrawlConfig]):
    """Crawls Bgee species pages extracting schema.org JSON-LD dataset records."""

    def __init__(self, config: BgeeCrawlConfig):
        super().__init__(config)
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        self._raw_output_path = output_dir / "bgee_raw.jsonl"
        self._processed_output_path = output_dir / "bgee_processed.jsonl"

    def create_client(self) -> BgeeClient:
        """Create Bgee API client."""
        return BgeeClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            max_retries=self.config.max_retries,
        )

    def create_iterator(self, client: ApiClient) -> AsyncIterable[Any]:
        """Create iterator over Bgee raw records."""
        bgee_client = cast(BgeeClient, client)
        opts = BgeeIteratorOpts(
            start_url=self.config.base_url,
            max_records=self.config.max_records,
        )
        return bgee_client.iterate_datasets(opts)

    def build_pipeline(self, client: ApiClient) -> ProcessorPipeline:  # noqa: ARG002
        """Build the processing pipeline."""
        return ProcessorPipeline(
            [
                # Parse schema:Dataset records to typed models
                ParserProcessor(parser=BgeeParser()),
                # Write raw parsed records
                JSONLWriter(output_path=self._raw_output_path),
                # Convert to Onedata format with DataCite metadata
                OnedataConverter(metadata_builder=BgeeDataCiteBuilder()), # type: ignore[type-arg]
                # Write processed records ready for registration
                JSONLWriter(output_path=self._processed_output_path),
            ]
        )

    async def after_crawl(self) -> None:
        """Print first record's DataCite XML for conformity check."""
        if self._processed_output_path.exists() and self._processed_output_path.stat().st_size > 0:
            try:
                with open(self._processed_output_path, encoding="utf-8") as f:
                    first_line = f.readline()
                    if first_line:
                        record = json.loads(first_line)
                        metadata_xml = record.get("metadata_xml", "")
                        if metadata_xml:
                            console.newline()
                            console.section("First Record DataCite XML (Conformity Check)")
                            # Pretty-print the XML
                            dom = minidom.parseString(metadata_xml)
                            pretty_xml = dom.toprettyxml(indent="  ")
                            # Remove XML declaration and extra blank lines
                            pretty_xml = "\n".join(
                                line for line in pretty_xml.split("\n")
                                if line.strip() and not line.startswith("<?xml")
                            )
                            console.print(pretty_xml)
            except Exception as e:  # pylint: disable=broad-except
                console.debug(f"Could not print first record DataCite XML: {e}")

    def get_max_items(self) -> int | None:
        """Return max records for progress tracking."""
        return self.config.max_records

    def _get_banner_subtitle(self) -> str | None:
        """Return banner subtitle with start URL."""
        return f"Start URL: {self.config.base_url}"
