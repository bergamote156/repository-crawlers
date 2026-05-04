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
from typing import Annotated, Any

from rich.table import Table

from crawlers.core import (
    CliAlias,
    CliPositional,
    CliSource,
    CrawlConfig,
    CrawlerPlugin,
    Err,
    HttpClient,
    HttpConfig,
    JsonObject,
    Result,
    RunContext,
    command,
    model_validator,
    opt,
)
from crawlers.core.dataset import OnedataDataset
from crawlers.plugins.eodc.api import EODCClient, EODCSearchParams
from crawlers.plugins.eodc.parser import parse_eodc_item
from crawlers.ui import console

_DESCRIPTION_PREVIEW_LEN = 80


class EODCApiConfig(HttpConfig):
    """Base configuration for EODC STAC API connections."""

    base_url: str = opt(
        "https://stac.eodc.eu/api/v1",
        description="EODC STAC API base URL",
    )


class EODCCrawlConfig(EODCApiConfig, CrawlConfig, kw_only=True):
    """Configuration for EODC STAC crawling."""

    collections: Annotated[str, CliPositional] = opt(
        description="STAC collections to crawl (comma-separated)",
    )

    intersects: JsonObject | None = opt(
        None,
        excluded_from=[CliSource],
        description="GeoJSON geometry for spatial filter",
    )

    datetime_range: Annotated[str | None, CliAlias("--datetime", "-d")] = opt(
        None,
        description="ISO datetime range (e.g. 2025-01-01/2025-01-31)",
    )

    page_size: int = opt(100, description="Items per STAC search page")

    @model_validator
    def _normalize_collections(self) -> None:
        if not self.collections or self.collections.isspace():
            raise ValueError("Collections cannot be empty")
        # `__init_subclass__` applies @dataclass without `frozen=True`, so
        # in-place rewrite is safe; keeps the contract that consumers see
        # the stripped form everywhere.
        object.__setattr__(self, "collections", self.collections.strip())

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

    # --- Banner / context plumbing ---

    def run_context_name(self, config: EODCCrawlConfig) -> str:
        collections = config.get_collections_list()
        return collections[0] if collections else "eodc"

    # --- Lifecycle ---

    async def setup(self, ctx: RunContext[EODCCrawlConfig], stack: AsyncExitStack) -> None:
        """Open the shared HttpClient and build the API façade."""
        http = await self._open_http(ctx.config, stack)
        self._api_client = EODCClient(http)

    # --- Iteration & parse ---

    async def iterate_datasets(self, ctx: RunContext[EODCCrawlConfig]) -> AsyncIterator[JsonObject]:
        """Yield STAC item dicts from the configured collections."""
        async for item in self._api_client.iterate_items(
            EODCSearchParams(
                collections=ctx.config.get_collections_list(),
                intersects=ctx.config.intersects,
                datetime_range=ctx.config.datetime_range,
                page_size=ctx.config.page_size,
                max_items=ctx.config.max_records,
            )
        ):
            yield item

    async def process(self, item: JsonObject, /) -> Result[OnedataDataset, Any] | None:
        """Map a STAC item into an `OnedataDataset`."""
        return parse_eodc_item(item)

    # ─────────────────────────────────────────────────────────────────────────────
    # Auxiliary commands
    # ─────────────────────────────────────────────────────────────────────────────

    @command
    async def list_collections(self, config: EODCApiConfig, stack: AsyncExitStack) -> None:
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
            desc = coll.get("description", "")[:_DESCRIPTION_PREVIEW_LEN]
            if len(coll.get("description", "")) > _DESCRIPTION_PREVIEW_LEN:
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
