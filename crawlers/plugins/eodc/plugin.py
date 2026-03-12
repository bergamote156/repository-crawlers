"""
EODC Plugin Definition.

Declarative plugin using @command decorator for CLI commands.
"""

# pylint: disable=import-outside-toplevel

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from rich.table import Table

from crawlers.core.plugin import CrawlerPlugin, command
from crawlers.core.ui import console
from crawlers.plugins.eodc.config import EODCApiConfig, EODCCrawlConfig


class EODCPlugin(CrawlerPlugin):
    """
    Plugin implementation for EODC STAC API.

    Provides commands:
    - crawl: Crawl STAC items from specified collections
    - list-collections: List available STAC collections
    """

    name = "eodc"
    description = "Crawler for EODC Earth Observation Data Centre STAC API"

    @command("crawl", EODCCrawlConfig, help="Crawl STAC items from collections")
    async def run_crawl(self, config: EODCCrawlConfig) -> None:
        """Execute crawling for the specified collections."""
        # Lazy import to avoid import overhead when not running this command
        from crawlers.plugins.eodc.crawler import EODCCrawler

        crawler = EODCCrawler(config)
        await crawler.run()

    @command("list-collections", EODCApiConfig, help="List available STAC collections")
    async def list_collections(self, config: EODCApiConfig) -> None:
        """List all available STAC collections from EODC."""
        # Lazy import
        from crawlers.plugins.eodc.api import EODCClient

        async with EODCClient(
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
        ) as client:
            with console.status("Fetching collections..."):
                collections = await client.get_collections()

            table = Table(
                title=f"Available Collections ({len(collections)})",
                show_header=True,
                header_style="bold",
            )
            table.add_column("ID", style="cyan", no_wrap=True)
            table.add_column("Title")
            table.add_column("Description", max_width=60)

            for coll in collections:
                coll_id = coll.get("id", "unknown")
                title = coll.get("title", "-")
                desc = coll.get("description", "")[:80]
                if len(coll.get("description", "")) > 80:
                    desc += "..."
                table.add_row(coll_id, title, desc)

            console.print(table)
