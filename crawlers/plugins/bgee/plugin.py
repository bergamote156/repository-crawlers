"""Bgee Plugin Definition."""

# pylint: disable=import-outside-toplevel

__author__ = "Vincent Emonet"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from crawlers.core.plugin import CrawlerPlugin, command
from crawlers.plugins.bgee.config import BgeeCrawlConfig


class BgeePlugin(CrawlerPlugin):
    """Plugin for Bgee gene expression database (schema.org JSON-LD harvesting)."""

    name = "bgee"
    description = "Crawler for Bgee gene expression database via schema.org JSON-LD"

    @command("crawl", BgeeCrawlConfig, help="Crawl Bgee species dataset pages")
    async def run_crawl(self, config: BgeeCrawlConfig) -> None:
        """Crawl Bgee species pages and extract schema.org JSON-LD dataset records."""
        from crawlers.plugins.bgee.crawler import BgeeCrawler

        crawler = BgeeCrawler(config)
        await crawler.run()
