"""Bgee Plugin."""

__author__ = "Vincent Emonet"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import json
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from typing import Any
from xml.dom import minidom

from crawlers.core import CrawlerPlugin, HttpClient, Result, RunContext
from crawlers.model.dataset import OnedataDataset, OnedataFile
from crawlers.plugins.bgee.api import BgeeClient, BgeeParser
from crawlers.plugins.bgee.models import (
    BgeeCrawlConfig,
    BgeeIteratorOpts,
    BgeeRawRecord,
)
from crawlers.ui import console


class BgeePlugin(CrawlerPlugin[BgeeRawRecord, BgeeCrawlConfig]):
    """Plugin for Bgee gene expression database (schema.org JSON-LD harvesting)."""

    name = "bgee"
    description = "Crawler for Bgee gene expression database via schema.org JSON-LD"

    config_class = BgeeCrawlConfig

    _api_client: BgeeClient
    _parser: BgeeParser
    _validation_http: HttpClient | None

    # --- Lifecycle ---

    async def setup(self, ctx: RunContext[BgeeCrawlConfig], stack: AsyncExitStack) -> None:
        """Open a shared `HttpClient` used for crawling and URL validation."""
        http = await stack.enter_async_context(HttpClient.from_config(ctx.config))
        self._api_client = BgeeClient(http)
        self._parser = BgeeParser()
        self._validation_http = None if ctx.config.no_url_validation else http

    # --- Iteration & parse ---

    async def iterate_datasets(
        self, ctx: RunContext[BgeeCrawlConfig]
    ) -> AsyncIterator[BgeeRawRecord]:
        """Yield raw Bgee records (rdflib graph + node) scraped from species pages."""
        opts = BgeeIteratorOpts(
            start_url=ctx.config.base_url,
            max_records=ctx.config.max_records,
        )
        async for record in self._api_client.iterate_datasets(opts):
            yield record

    async def process(self, raw: BgeeRawRecord, /) -> Result[OnedataDataset, Any] | None:
        """Parse a schema.org Dataset node and build an `OnedataDataset`."""
        bgee_dataset = self._parser.parse(raw)
        if bgee_dataset is None:
            return None

        return await OnedataDataset.build(
            pid=bgee_dataset.identifier,
            name=bgee_dataset.title,
            location=bgee_dataset.title.replace("/", "-"),
            metadata=bgee_dataset.metadata_record,
            files=[OnedataFile(path=f.path, url=f.url) for f in bgee_dataset.files],
            http=self._validation_http,
        )

    # --- Post-run hook (preserved from the original DefaultCrawlerPlugin impl) ---

    async def after_crawl(self, ctx: RunContext[BgeeCrawlConfig]) -> None:
        """Print first record's DataCite XML for conformity check."""
        processed_path = ctx.processed_sink.path
        if not (processed_path.exists() and processed_path.stat().st_size > 0):
            return
        try:
            with open(processed_path, encoding="utf-8") as f:
                first_line = f.readline()
            record = json.loads(first_line)
            metadata_xml = record.get("metadata_xml", "")
            if metadata_xml:
                console.newline()
                console.section("First Record DataCite XML (Conformity Check)")
                dom = minidom.parseString(metadata_xml)
                pretty_xml = "\n".join(
                    line
                    for line in dom.toprettyxml(indent="  ").split("\n")
                    if line.strip() and not line.startswith("<?xml")
                )
                console.print(pretty_xml)
        except Exception as e:  # pylint: disable=broad-except
            console.debug(f"Could not print first record DataCite XML: {e}")
