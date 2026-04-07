"""
EODC Plugin (default architecture).

Single-class plugin for EODC STAC API using DefaultCrawlerPlugin.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from typing import cast

from rich.table import Table

from crawlers.core.plugin import command
from crawlers.core.result import Err
from crawlers.default.config import DefaultCrawlConfig
from crawlers.default.plugin import DefaultCrawlerPlugin, DefaultCrawlSpec
from crawlers.plugins.eodc.api import EODCClient, EODCSearchOpts
from crawlers.plugins.eodc.config import EODCApiConfig, EODCCrawlConfig
from crawlers.plugins.eodc.parser import EODCParser
from crawlers.ui import console


class EODCPlugin(DefaultCrawlerPlugin):
    """
    EODC STAC API crawler using the default plugin architecture.
    """

    name = "eodc"
    description = "Crawler for EODC STAC API (default architecture)"
    config_class = EODCCrawlConfig

    def prepare_crawl(self, config: DefaultCrawlConfig) -> DefaultCrawlSpec:
        cfg = cast(EODCCrawlConfig, config)

        collections = cfg.get_collections_list()
        iterator_opts = EODCSearchOpts(
            collections=collections,
            intersects=cfg.intersects,
            datetime=cfg.datetime_range,
            limit=cfg.page_size,
            max_items=cfg.max_records,
        )

        return DefaultCrawlSpec(
            client=EODCClient.from_config(cfg),
            iterator_opts=iterator_opts,
            parser=EODCParser(),
            run_context_name=collections[0] if collections else "eodc",
            banner_subtitle=f"Collections: {', '.join(collections)}",
        )

    @command("list-collections", EODCApiConfig, help="List available STAC collections")
    async def list_collections(self, config: EODCApiConfig) -> None:
        """List all available STAC collections from EODC."""
        async with EODCClient.from_config(config) as client:
            with console.status("Fetching collections..."):
                result = await client.get_collections()

            if isinstance(result, Err):
                console.error(f"Failed to fetch collections: {result.value}")
                return

            collections = result.value

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
