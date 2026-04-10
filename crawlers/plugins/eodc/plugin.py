"""
EODC Plugin.

Crawler plugin for the EODC Earth Observation Data Centre STAC API.
Built on `CrawlerPlugin`: paginates `POST /search` for one or
more STAC collections and delegates DataCite mapping to `eodc.parser`.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from typing import Any

from rich.table import Table

from crawlers.core import (
    CrawlConfig,
    CrawlerPlugin,
    Err,
    HttpClient,
    HttpConfig,
    Result,
    RunContext,
    command,
    opt,
)
from crawlers.model.dataset import OnedataDataset, OnedataFile
from crawlers.plugins.eodc.api import EODCClient
from crawlers.plugins.eodc.parser import parse_eodc_item
from crawlers.ui import console


class EODCApiConfig(HttpConfig):
    """Base configuration for EODC STAC API connections."""

    base_url: str = opt(
        "https://stac.eodc.eu/api/v1",
        description="EODC STAC API base URL",
    )


class EODCCrawlConfig(EODCApiConfig, CrawlConfig, kw_only=True):
    """Configuration for EODC STAC crawling."""

    collections: str = opt(
        ...,
        # Explicit CLI is needed for positional args to be detected correctly
        # (otherwise '--' will be prepended)
        cli="collections",
        description="STAC collections to crawl (comma-separated)",
    )

    intersects: dict | None = opt(
        None,
        cli=False,
        yaml_key="intersects",
        description="GeoJSON geometry for spatial filter",
    )

    datetime_range: str | None = opt(
        None,
        cli=("--datetime", "-d"),
        description="ISO datetime range (e.g. 2025-01-01/2025-01-31)",
    )

    page_size: int = opt(100, description="Items per STAC search page")

    def __post_init__(self):
        if not self.collections or self.collections.isspace():
            raise ValueError("Collections cannot be empty")

        self.collections = self.collections.strip()

    def get_collections_list(self) -> list[str]:
        """Return collections as a list of stripped strings."""
        return [c.strip() for c in self.collections.split(",") if c.strip()]


class EODCPlugin(CrawlerPlugin[dict, EODCCrawlConfig]):
    """Crawler for the EODC Earth Observation Data Centre STAC API."""

    name = "eodc"
    description = "Crawler for EODC STAC API"

    # ─────────────────────────────────────────────────────────────────────────────
    # Crawling
    # ─────────────────────────────────────────────────────────────────────────────

    config_class = EODCCrawlConfig

    _api_client: EODCClient
    _validation_http: HttpClient | None

    # --- Banner / context plumbing ---

    def run_context_name(self, config: EODCCrawlConfig) -> str:
        collections = config.get_collections_list()
        return collections[0] if collections else "eodc"

    # --- Lifecycle ---

    async def setup(
        self, ctx: RunContext[EODCCrawlConfig], stack: AsyncExitStack
    ) -> None:
        """Open the shared HttpClient and build the API façade."""
        http = await self._open_http(ctx.config, stack)
        self._api_client = EODCClient(http)
        self._validation_http = None if ctx.config.no_url_validation else http

    # --- Iteration & parse ---

    async def iterate_datasets(
        self, ctx: RunContext[EODCCrawlConfig]
    ) -> AsyncIterator[dict]:
        """Yield STAC item dicts from the configured collections."""
        async for item in self._api_client.iterate_items(
            ctx.config.get_collections_list(),
            intersects=ctx.config.intersects,
            datetime=ctx.config.datetime_range,
            page_size=ctx.config.page_size,
            max_items=ctx.config.max_records,
        ):
            yield item

    async def process(self, item: dict) -> Result[OnedataDataset, Any] | None:
        """Map a STAC item into an `OnedataDataset`."""
        parsed = parse_eodc_item(item)
        if parsed is None:
            return None

        return await OnedataDataset.build(
            pid=parsed.identifier,
            name=parsed.title,
            location=parsed.title.replace("/", "-"),
            metadata=parsed.metadata,
            files=[OnedataFile(path=f.path, url=f.url) for f in parsed.files],
            http=self._validation_http,
        )

    # ─────────────────────────────────────────────────────────────────────────────
    # Auxiliary commands
    # ─────────────────────────────────────────────────────────────────────────────

    @command
    async def list_collections(
        self, config: EODCApiConfig, stack: AsyncExitStack
    ) -> None:
        """List all available STAC collections from EODC."""
        http = await self._open_http(config, stack)
        client = EODCClient(http)

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

    # ─────────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────────

    @staticmethod
    async def _open_http(config: EODCApiConfig, stack: AsyncExitStack) -> HttpClient:
        """Open a shared `HttpClient` for the EODC STAC API on `stack`."""
        return await stack.enter_async_context(HttpClient.from_config(config))
