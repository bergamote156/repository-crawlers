"""Bgee Plugin - CLI commands."""

__author__ = "Vincent Emonet"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from crawlers.core.config import ApiConfig, BaseCrawlConfig, opt
from crawlers.core.plugin import CrawlerPlugin, command


class BgeeApiConfig(ApiConfig):
    """Base configuration for Bgee connections."""

    base_url: str = opt(
        "https://bgee.org/search/species",
        description="Bgee species listing page URL to start harvesting from",
    )


class BgeeCrawlConfig(BgeeApiConfig, BaseCrawlConfig, kw_only=True):
    """Full configuration for Bgee schema.org JSON-LD crawling."""

    max_records: int | None = opt(
        None,
        cli=("-n", "--max-records"),
        description="Maximum number of datasets to fetch",
    )


class BgeePlugin(CrawlerPlugin):
    """Plugin for Bgee gene expression database (schema.org JSON-LD harvesting)."""

    name = "bgee"
    description = "Crawler for Bgee gene expression database via schema.org JSON-LD"

    @command("crawl", BgeeCrawlConfig, help="Crawl Bgee species dataset pages")
    async def run_crawl(self, config: BgeeCrawlConfig) -> None:
        """Crawl Bgee species pages and extract schema.org JSON-LD dataset records."""
        from crawlers.plugins.bgee.crawler import BgeeCrawler  # avoid circular import

        crawler = BgeeCrawler(config)
        await crawler.run()
