"""
Ecudo Plugin.

Crawler plugin for eCUDO.pl science data repositories.
"""

# pylint: disable=import-outside-toplevel

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import sys
from typing import cast

from rich.table import Table

from crawlers.core.abc.plugin import command
from crawlers.core.default.config import DefaultCrawlConfig
from crawlers.core.default.plugin import CrawlSpec, DefaultCrawlerPlugin
from crawlers.core.default.workspace import DefaultRunContext
from crawlers.core.errors import MatchError
from crawlers.core.metadata.openaire import OpenAIREBuilder
from crawlers.core.processors.converters import OnedataConverter
from crawlers.core.processors.fetchers import DatasetFetcher
from crawlers.core.processors.filters import DiversityFilter
from crawlers.core.processors.pipeline import ProcessorPipeline
from crawlers.core.processors.tap import Tap
from crawlers.core.processors.validators import URLValidator
from crawlers.core.result import Err, Ok
from crawlers.core.ui import console
from crawlers.plugins.ecudo.api import EcudoClient, EcudoIteratorOpts
from crawlers.plugins.ecudo.config import EcudoApiConfig, EcudoCrawlConfig
from crawlers.plugins.ecudo.models import EcudoDataset
from crawlers.plugins.ecudo.parser import EcudoParser


class EcudoPlugin(DefaultCrawlerPlugin):
    """
    Plugin for eCUDO.pl science data repositories.

    Commands:
    - crawl: Crawl datasets from an organization
    - list-orgs: List available organizations
    """

    name = "ecudo"
    description = "Crawler for eCUDO.pl science data repositories"
    config_class = EcudoCrawlConfig  # type: ignore[assignment]
    _crawl_config: EcudoCrawlConfig

    def prepare_crawl(self, config: DefaultCrawlConfig) -> CrawlSpec:
        cfg = cast(EcudoCrawlConfig, config)
        self._crawl_config = cfg

        client = EcudoClient(
            base_url=cfg.base_url,
            timeout=cfg.timeout,
            max_retries=cfg.max_retries,
        )
        return CrawlSpec(
            client=client,
            iterator_opts=EcudoIteratorOpts(
                org_id=cfg.organization,
                page_size=cfg.page_size,
                max_datasets=cfg.max_records,
            ),
            parser=EcudoParser(),
            metadata_builder=OpenAIREBuilder(),
            run_context_name=cfg.organization,
            banner_subtitle=f"Organization: {cfg.organization}",
            max_items=cfg.max_records,
            url_validation=cfg.get_url_validator_enabled(),
        )

    def build_pipeline(
        self, spec: CrawlSpec, ctx: DefaultRunContext
    ) -> ProcessorPipeline:
        ecudo_client = cast(EcudoClient, spec.client)
        cfg = self._crawl_config
        df_cfg = cfg.processors.diversity_filter

        return ProcessorPipeline(
            processors=[
                DatasetFetcher[dict, EcudoDataset](
                    fetch_fn=ecudo_client.get_dataset_metadata,
                    parser=spec.parser,
                ),
                URLValidator[EcudoDataset](  # type: ignore[type-var]
                    validate_fn=ecudo_client.validate_url,
                    enabled=spec.url_validation,
                ),
                DiversityFilter[EcudoDataset](
                    max_similar=df_cfg.max_similar,
                    similarity_threshold=df_cfg.similarity_threshold,
                    enabled=cfg.get_diversity_filter_enabled(),
                ),
                Tap(ctx.raw_sink, transform=lambda d: d.to_json()),
                OnedataConverter[EcudoDataset](  # type: ignore[type-var]
                    metadata_builder=spec.metadata_builder,
                ),
                Tap(ctx.processed_sink, transform=lambda d: d.to_json()),
            ],
            rejection_sink=ctx.rejection_sink,
        )

    async def before_crawl(self, spec: CrawlSpec) -> None:
        """Validate that the requested organization exists."""
        ecudo_client = cast(EcudoClient, spec.client)

        with console.status("Validating organization..."):
            result = await ecudo_client.get_organizations()

        match result:
            case Err(value=err):
                console.error(f"Failed to fetch organizations: {err}")
                sys.exit(1)
            case Ok(value=orgs):
                org = self._crawl_config.organization
                if not any(o["id"] == org for o in orgs):
                    console.error(f"Organization '{org}' not found.")
                    console.error(f"Available: {', '.join(o['id'] for o in orgs)}")
                    sys.exit(1)
            case other:
                raise MatchError(other)

        console.success(f"Found organization: {self._crawl_config.organization}")

    @command("list-orgs", EcudoApiConfig, help="List available organizations")
    async def list_organizations(self, config: EcudoApiConfig) -> None:
        """List all available organizations from Ecudo."""
        async with EcudoClient(
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
        ) as client:
            with console.status("Fetching organizations..."):
                result = await client.get_organizations()

            if result.is_err():
                console.error(f"Failed to fetch organizations: {result.err()}")
                return

            organizations = result.unwrap()

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
