"""
VIP Plugin.

Crawler for VIP (Virtual Imaging Platform) Girder REST API.
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
from crawlers.plugins.vip.api import VipClient, VipIteratorOpts
from crawlers.plugins.vip.config import VipApiConfig, VipCrawlConfig
from crawlers.plugins.vip.metadata import VipDataCiteBuilder
from crawlers.plugins.vip.parser import VipParser
from crawlers.ui import console


class VipPlugin(DefaultCrawlerPlugin):
    """
    VIP (Virtual Imaging Platform) crawler using the default plugin architecture.

    Crawls Girder collections exposed by the VIP platform, recursively
    collecting all nested files for each top-level dataset folder.
    """

    name = "vip"
    description = "Crawler for VIP (Virtual Imaging Platform) Girder REST API"
    config_class = VipCrawlConfig

    def prepare_crawl(self, config: DefaultCrawlConfig) -> DefaultCrawlSpec:
        cfg = cast(VipCrawlConfig, config)

        return DefaultCrawlSpec(
            client=VipClient(
                base_url=cfg.base_url,
                timeout=cfg.timeout,
                max_retries=cfg.max_retries,
            ),
            iterator_opts=VipIteratorOpts(
                collection=cfg.collection,
                page_size=cfg.page_size,
                max_records=cfg.max_records,
            ),
            parser=VipParser(),
            metadata_builder=VipDataCiteBuilder(),
            run_context_name=cfg.collection,
            banner_subtitle=f"Collection: {cfg.collection}",
        )

    @command("list-collections", VipApiConfig, help="List available VIP collections")
    async def list_collections(self, config: VipApiConfig) -> None:
        """List all collections available in the VIP Girder instance."""
        async with VipClient(
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
        ) as client:
            with console.status("Fetching collections..."):
                result = await client.list_collections()

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
        table.add_column("Name", style="green")
        table.add_column("Description", max_width=60)
        table.add_column("Size", justify="right")

        for coll in collections:
            coll_id = coll.get("_id", "unknown")
            name = coll.get("name", "-")
            desc = coll.get("description", "") or ""
            if len(desc) > 80:
                desc = desc[:77] + "..."
            size = coll.get("size", 0)
            size_str = _format_size(size)
            table.add_row(coll_id, name, desc, size_str)

        console.print(table)


def _format_size(size_bytes: int) -> str:
    """Format byte size as a human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes:.1f} PB"
