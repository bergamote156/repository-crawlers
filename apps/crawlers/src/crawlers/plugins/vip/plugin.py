"""
VIP Plugin.

Crawler plugin for VIP (Virtual Imaging Platform) Girder REST API.
Built on `CrawlerPlugin`: iterates top-level dataset folders in
a named collection, resolves each folder's files recursively, and
delegates DataCite mapping to `vip.parser`.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from typing import Annotated, Any

from rich.table import Table

from crawlers.core import (
    CliPositional,
    CrawlConfig,
    CrawlerPlugin,
    Err,
    HttpClient,
    HttpConfig,
    JsonObject,
    Ok,
    Result,
    RunContext,
    command,
    model_validator,
    opt,
)
from crawlers.core.dataset import OnedataDataset
from crawlers.plugins.vip.api import VipClient
from crawlers.plugins.vip.parser import parse_vip_record
from crawlers.ui import console

_BYTES_PER_UNIT = 1024
_DESCRIPTION_PREVIEW_LEN = 80
_ELLIPSIS = "..."


class VipApiConfig(HttpConfig):
    """Base configuration for VIP Girder API connections."""

    base_url: str = opt(
        "https://srmnopt.creatis.insa-lyon.fr/api/v1",
        description="VIP Girder REST API base URL",
    )


class VipCrawlConfig(VipApiConfig, CrawlConfig, kw_only=True):
    """Configuration for VIP Girder collection crawling."""

    collection: Annotated[str, CliPositional] = opt(
        description="Name of the VIP collection to crawl",
    )

    page_size: int = opt(100, description="Items per API page")

    @model_validator
    def _normalize_collection(self) -> None:
        if not self.collection or self.collection.isspace():
            raise ValueError("Collection name cannot be empty")
        object.__setattr__(self, "collection", self.collection.strip())


class VipPlugin(CrawlerPlugin[JsonObject, VipCrawlConfig]):
    """Crawler for VIP (Virtual Imaging Platform) Girder collections."""

    name = "vip"
    description = "Crawler for VIP (Virtual Imaging Platform) Girder REST API"

    # ─────────────────────────────────────────────────────────────────────────────
    # Crawling
    # ─────────────────────────────────────────────────────────────────────────────

    config_class = VipCrawlConfig

    _api_client: VipClient

    # --- Banner / context plumbing ---

    def run_context_name(self, config: VipCrawlConfig) -> str:
        return config.collection

    # --- Lifecycle ---

    async def setup(self, ctx: RunContext[VipCrawlConfig], stack: AsyncExitStack) -> None:
        """Open the shared HttpClient and build the API façade."""
        http = await self._open_http(ctx.config, stack)
        self._api_client = VipClient(http)

    # --- Iteration & parse ---

    async def iterate_datasets(self, ctx: RunContext[VipCrawlConfig]) -> AsyncIterator[JsonObject]:
        """Yield raw Girder folder dicts (one per top-level dataset)."""
        async for folder in self._api_client.iterate_datasets(
            ctx.config.collection,
            page_size=ctx.config.page_size,
            max_records=ctx.config.max_records,
        ):
            yield folder

    async def process(self, folder: JsonObject, /) -> Result[OnedataDataset, Any] | None:
        """Resolve a folder's files and map them to an `OnedataDataset`."""
        files = await self._api_client.resolve_dataset_files(folder)

        dataset = parse_vip_record(folder, files)
        if dataset is None:
            return None

        return Ok(dataset)

    # ─────────────────────────────────────────────────────────────────────────────
    # Auxiliary commands
    # ─────────────────────────────────────────────────────────────────────────────

    @command
    async def list_collections(self, config: VipApiConfig, stack: AsyncExitStack) -> None:
        """List all collections available in the VIP Girder instance."""
        http = await self._open_http(config, stack)
        client = VipClient(http)

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
            if len(desc) > _DESCRIPTION_PREVIEW_LEN:
                desc = desc[: _DESCRIPTION_PREVIEW_LEN - len(_ELLIPSIS)] + _ELLIPSIS
            size = coll.get("size", 0)
            table.add_row(coll_id, name, desc, _format_size(size))

        console.print(table)

    # ─────────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────────

    @staticmethod
    async def _open_http(config: VipApiConfig, stack: AsyncExitStack) -> HttpClient:
        """Open a shared `HttpClient` for the VIP Girder API on `stack`."""
        return await stack.enter_async_context(
            HttpClient.from_config(config, extra_headers={"Accept-Language": "en"})
        )


def _format_size(size_bytes: int) -> str:
    """Format byte size as a human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < _BYTES_PER_UNIT:
            return f"{size_bytes:.1f} {unit}"
        size_bytes //= _BYTES_PER_UNIT
    return f"{size_bytes:.1f} PB"
