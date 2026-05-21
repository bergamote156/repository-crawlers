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
import re

from rich.table import Table

from crawlers.core import (
    CrawlConfig,
    CrawlerPlugin,
    Err,
    HttpClient,
    HttpConfig,
    JsonObject,
    Result,
    RunContext,
    command,
    opt,
)
from crawlers.model.dataset import OnedataDataset, OnedataFile
from crawlers.plugins.eodc.api import EODCClient, EODCSearchParams
from crawlers.plugins.eodc.parser import parse_eodc_collection, parse_eodc_item
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

    collections: str = opt(
        ...,
        # Explicit CLI is needed for positional args to be detected correctly
        # (otherwise '--' will be prepended)
        cli="collections",
        description="STAC collections to crawl (comma-separated)",
    )

    intersects: JsonObject | None = opt(
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
    _collection_cache: dict[str, JsonObject]

    # --- Banner / context plumbing ---

    def run_context_name(self, config: EODCCrawlConfig) -> str:
        collections = config.get_collections_list()
        return collections[0] if collections else "eodc"

    # --- Lifecycle ---

    async def setup(self, ctx: RunContext[EODCCrawlConfig], stack: AsyncExitStack) -> None:
        """Open the shared HttpClient and build the API façade."""
        http = await self._open_http(ctx.config, stack)
        self._api_client = EODCClient(http)
        self._validation_http = None if ctx.config.no_url_validation else http
        self._collection_cache = {}
        await self._prefetch_collections(ctx.config)

    async def _prefetch_collections(self, config: EODCCrawlConfig) -> None:
        """Fetch configured collection metadata up front and cache it."""
        for collection_id in config.get_collections_list():
            result = await self._api_client.get_collection(collection_id)
            if isinstance(result, Err):
                console.warning(f"Failed to fetch metadata for collection {collection_id}: {result.value}")
                continue
            self._collection_cache[collection_id] = result.value

    async def _get_collection_meta(self, collection_id: str | None) -> JsonObject | None:
        """Return cached collection metadata, fetching it if needed."""
        if not collection_id:
            return None

        if collection_id in self._collection_cache:
            return self._collection_cache[collection_id]

        result = await self._api_client.get_collection(collection_id)
        if isinstance(result, Err):
            console.warning(f"Failed to fetch metadata for collection {collection_id}: {result.value}")
            return None

        self._collection_cache[collection_id] = result.value
        return result.value

    # --- Iteration & parse ---

    async def iterate_datasets(self, ctx: RunContext[EODCCrawlConfig]) -> AsyncIterator[JsonObject | tuple[str, JsonObject]]:
        """
        Yield STAC item dicts or collection tuples if a collection has no items.
        """
        collections = ctx.config.get_collections_list()

        for collection_id in collections:
            console.debug(f"Fetching items for collection: {collection_id}")

            items_found = False

            async for item in self._api_client.iterate_items(
                EODCSearchParams(
                    collections=[collection_id],
                    intersects=ctx.config.intersects,
                    datetime_range=ctx.config.datetime_range,
                    page_size=ctx.config.page_size,
                    max_items=ctx.config.max_records,
                )
            ):
                items_found = True
                yield item

            # fallback: no items → use collection-level assets
            if not items_found:
                collection_meta = await self._get_collection_meta(collection_id)
                if collection_meta:
                    console.debug(f"Falling back to collection-level assets for {collection_id}")
                    yield ("collection", collection_meta)

    async def process(self, item: JsonObject | tuple[str, JsonObject], /) -> Result[OnedataDataset, Any] | None:
        """Map STAC item or collection into an `OnedataDataset`."""

        # Case 1: collection-level dataset
        if isinstance(item, tuple) and item[0] == "collection":
            collection_meta = item[1]

            parsed = parse_eodc_collection(collection_meta)
            if parsed is None:
                return None

            return await OnedataDataset.build(
                pid=parsed.identifier,
                name=parsed.title,
                location=self._build_dataset_location(parsed.identifier, parsed.title),
                metadata=parsed.metadata,
                files=[OnedataFile(path=f.path, url=f.url) for f in parsed.files],
                http=self._validation_http,
            )

        # Case 2: normal STAC item
        collection_id = item.get("collection")
        collection_meta = await self._get_collection_meta(collection_id if isinstance(collection_id, str) else None)

        parsed = parse_eodc_item(item, collection_meta)
        if parsed is None:
            return None

        return await OnedataDataset.build(
            pid=parsed.identifier,
            name=parsed.title,
            location=self._build_dataset_location(parsed.identifier, parsed.title),
            metadata=parsed.metadata,
            files=[OnedataFile(path=f.path, url=f.url) for f in parsed.files],
            http=self._validation_http,
        )
    

    def _build_dataset_location(self, item_id: str, title: str) -> str:
        """Generate a stable dataset location from the item identifier or title."""
        candidate = item_id or title or "eodc-dataset"
        sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", candidate)
        sanitized = sanitized.strip("-_ .")
        return sanitized or "eodc-dataset"

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
