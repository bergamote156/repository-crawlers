"""
Ecudo Plugin.

Crawler plugin for eCUDO.pl science data repositories. Built on
`CrawlerPlugin`: pulls JSON-LD records from the eCUDO REST
API, delegates mapping to `ecudo.parser`, and lets the framework
persist processed/rejected datasets.
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
from crawlers.plugins.ecudo.api import EcudoApiClient
from crawlers.plugins.ecudo.parser import parse_ecudo_record
from crawlers.ui import console


class EcudoApiConfig(HttpConfig):
    """Configuration for Ecudo API connections."""

    base_url: str = opt("http://central.ecudo.pl", description="Ecudo API base URL")


class EcudoCrawlConfig(EcudoApiConfig, CrawlConfig, kw_only=True):
    """Ecudo crawl configuration."""

    organization: str = opt(
        ...,
        # Explicit CLI is needed for positional args to be detected correctly
        # (otherwise '--' will be prepended)
        cli="organization",
        description="Organization ID (e.g. iopan)",
    )

    page_size: int = opt(200, description="Items per API page")


class EcudoPlugin(CrawlerPlugin[str, EcudoCrawlConfig]):
    """Crawler for eCUDO.pl science data repositories."""

    name = "ecudo"
    description = "Crawler for eCUDO.pl science data repositories"

    # ─────────────────────────────────────────────────────────────────────────────
    # Crawling
    # ─────────────────────────────────────────────────────────────────────────────

    config_class = EcudoCrawlConfig

    _api_client: EcudoApiClient
    _validation_http: HttpClient | None

    # --- Banner / context plumbing ---

    def run_context_name(self, config: EcudoCrawlConfig) -> str:
        return config.organization

    # --- Lifecycle ---

    async def setup(self, ctx: RunContext[EcudoCrawlConfig], stack: AsyncExitStack) -> None:
        """Open the shared HttpClient and build the API façade."""
        http = await self._open_http(ctx.config, stack)
        self._api_client = EcudoApiClient(http)
        self._validation_http = None if ctx.config.no_url_validation else http

    async def before_crawl(self, ctx: RunContext[EcudoCrawlConfig]) -> None:
        """Verify the requested organization exists before producing items."""
        target_organization = ctx.config.organization

        with console.status("Validating organization..."):
            result = await self._api_client.get_organizations()

        if isinstance(result, Err):
            raise RuntimeError(f"Failed to fetch organizations: {result.value}")

        all_organizations = result.value
        if not any(o["id"] == target_organization for o in all_organizations):
            available = ", ".join(o["id"] for o in all_organizations)
            raise RuntimeError(
                f"Organization '{target_organization}' not found. Available: {available}"
            )

        console.success(f"Found organization: {target_organization}")

    # --- Iteration & parse ---

    async def iterate_datasets(self, ctx: RunContext[EcudoCrawlConfig]) -> AsyncIterator[str]:
        """Yield dataset IDs to feed the worker pool."""
        async for dataset_id in self._api_client.iterate_dataset_ids(
            ctx.config.organization,
            page_size=ctx.config.page_size,
            max_datasets=ctx.config.max_records,
        ):
            yield dataset_id

    async def process(self, dataset_id: str, /) -> Result[OnedataDataset, Any] | None:
        """Resolve a dataset ID to JSON-LD and build an `OnedataDataset`."""
        fetch_result = await self._api_client.get_dataset_metadata(dataset_id)
        if isinstance(fetch_result, Err):
            return fetch_result

        parsed = parse_ecudo_record(fetch_result.value)
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

    @command(name="list-orgs")
    async def list_organizations(self, config: EcudoApiConfig, stack: AsyncExitStack) -> None:
        """List all available organizations from Ecudo."""
        http = await self._open_http(config, stack)
        api_client = EcudoApiClient(http)

        with console.status("Fetching organizations..."):
            result = await api_client.get_organizations()

        if isinstance(result, Err):
            console.error(f"Failed to fetch organizations: {result.value}")
            return

        organizations = result.value

        table = Table(
            title=f"Available Organizations ({len(organizations)})",
            show_header=True,
            header_style="bold",
        )
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Name")

        for org in organizations:
            table.add_row(org.get("id", "unknown"), org.get("name", "-"))

        console.print(table)

    # ─────────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────────

    @staticmethod
    async def _open_http(config: EcudoApiConfig, stack: AsyncExitStack) -> HttpClient:
        """Open a shared `HttpClient` for the eCUDO API on `stack`."""
        return await stack.enter_async_context(
            HttpClient.from_config(config, extra_headers={"Accept-Language": "en"})
        )
