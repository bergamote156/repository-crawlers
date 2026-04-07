"""Bgee Plugin - CLI commands."""

__author__ = "Vincent Emonet"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import json
from typing import cast
from xml.dom import minidom

from crawlers.default.config import DefaultCrawlConfig
from crawlers.default.plugin import (
    DefaultCrawlerPlugin,
    DefaultCrawlSpec,
    DefaultRunContext,
)
from crawlers.plugins.bgee.api import BgeeClient, BgeeParser
from crawlers.plugins.bgee.models import BgeeCrawlConfig, BgeeIteratorOpts
from crawlers.ui import console


class BgeePlugin(DefaultCrawlerPlugin):
    """Plugin for Bgee gene expression database (schema.org JSON-LD harvesting)."""

    name = "bgee"
    description = "Crawler for Bgee gene expression database via schema.org JSON-LD"
    config_class = BgeeCrawlConfig

    def prepare_crawl(self, config: DefaultCrawlConfig) -> DefaultCrawlSpec:
        cfg = cast(BgeeCrawlConfig, config)

        return DefaultCrawlSpec(
            client=BgeeClient(
                base_url=cfg.base_url,
                timeout=cfg.timeout,
                max_retries=cfg.max_retries,
            ),
            iterator_opts=BgeeIteratorOpts(
                start_url=cfg.base_url, max_records=cfg.max_records
            ),
            parser=BgeeParser(),
            run_context_name=self.name,
            banner_subtitle=f"Start URL: {cfg.base_url}",
        )

    async def after_crawl(self, ctx: DefaultRunContext) -> None:
        """Print first record's DataCite XML for conformity check."""
        if not (
            ctx.processed_sink.path.exists()
            and ctx.processed_sink.path.stat().st_size > 0
        ):
            return
        try:
            with open(ctx.processed_sink.path, encoding="utf-8") as f:
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
