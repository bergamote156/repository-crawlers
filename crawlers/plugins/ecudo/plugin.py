"""
Ecudo Plugin Definition.

Declarative plugin using @command decorator for CLI commands.
"""

# pylint: disable=import-outside-toplevel

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from crawlers.core import output
from crawlers.core.plugin import CrawlerPlugin, command
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

        output.set_level(config.log_level)
        output.info(f"Starting crawl for organization: {config.organization}")
        output.debug(f"Configuration: {config}")

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
            orgs = await client.get_organizations()

            output.info(f"Found {len(orgs)} organizations:")
            for org in orgs:
                print(f"  {org['id']}: {org['name']}")
