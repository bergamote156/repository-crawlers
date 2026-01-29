"""
Ecudo Plugin Definition.

Declarative plugin using @command decorator for CLI commands.
"""

# pylint: disable=import-outside-toplevel

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from rich.table import Table

from crawlers.core.plugin import CrawlerPlugin, command
from crawlers.core.ui import console
from crawlers.plugins.ecudo.config import EcudoApiConfig, EcudoCrawlConfig


class EcudoPlugin(CrawlerPlugin):
    """
    Plugin implementation for Ecudo.

    Provides commands:
    - crawl: Crawl datasets from an organization
    - list-orgs: List available organizations
    """

    name = "ecudo"
    description = "Crawler for eCUDO.pl science data repositories"

    @command("crawl", EcudoCrawlConfig, help="Crawl datasets from organization")
    async def run_crawl(self, config: EcudoCrawlConfig) -> None:
        """Execute crawling for the specified organization."""
        # Lazy import to avoid import overhead when not running this command
        from crawlers.plugins.ecudo.crawler import EcudoCrawler

        crawler = EcudoCrawler(config)
        await crawler.run()

    @command("list-orgs", EcudoApiConfig, help="List available organizations")
    async def list_organizations(self, config: EcudoApiConfig) -> None:
        """List all available organizations from Ecudo."""
        # Lazy import
        from crawlers.plugins.ecudo.api import EcudoClient

        async with EcudoClient(
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
        ) as client:
            with console.status("Fetching organizations..."):
                organizations = await client.get_organizations()

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
