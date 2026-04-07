"""
Ecudo Plugin.

Crawler plugin for eCUDO.pl science data repositories.
"""

# pylint: disable=import-outside-toplevel

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import sys
from typing import assert_never, cast

from rich.table import Table

from crawlers.core.plugin import command
from crawlers.core.result import Err, Ok
from crawlers.default.config import DefaultCrawlConfig
from crawlers.default.plugin import DefaultCrawlerPlugin, DefaultCrawlSpec
from crawlers.default.workspace import DefaultRunContext
from crawlers.metadata.openaire import OpenAIREBuilder, OpenAIRERecord
from crawlers.plugins.ecudo.api import EcudoClient, EcudoIteratorOpts
from crawlers.plugins.ecudo.config import EcudoApiConfig, EcudoCrawlConfig
from crawlers.plugins.ecudo.parser import EcudoDataset, EcudoParser
from crawlers.processors.converters import OnedataConverter
from crawlers.processors.filters import DiversityFilter
from crawlers.processors.pipeline import ProcessorPipeline
from crawlers.processors.resolvers import DatasetResolver
from crawlers.processors.tap import Tap
from crawlers.processors.validators import URLValidator
from crawlers.ui import console


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

    def prepare_crawl(self, config: DefaultCrawlConfig) -> DefaultCrawlSpec:
        cfg = cast(EcudoCrawlConfig, config)
        self._crawl_config = cfg

        return DefaultCrawlSpec(
            client=EcudoClient(
                base_url=cfg.base_url,
                timeout=cfg.timeout,
                max_retries=cfg.max_retries,
            ),
            iterator_opts=EcudoIteratorOpts(
                org_id=cfg.organization,
                page_size=cfg.page_size,
                max_datasets=cfg.max_records,
            ),
            parser=EcudoParser(),
            metadata_builder=OpenAIREBuilder(),
            run_context_name=cfg.organization,
            banner_subtitle=f"Organization: {cfg.organization}",
        )

    def build_pipeline(self, ctx: DefaultRunContext) -> ProcessorPipeline:
        ecudo_client = cast(EcudoClient, ctx.crawl_spec.client)
        cfg = cast(EcudoCrawlConfig, ctx.config)
        df_cfg = cfg.diversity_filter

        return ProcessorPipeline(
            processors=[
                DatasetResolver[str, dict, EcudoDataset](
                    resolve_fn=ecudo_client.get_dataset_metadata,
                    parser=ctx.crawl_spec.parser,
                ),
                URLValidator[EcudoDataset](  # type: ignore[type-var]
                    validate_fn=ecudo_client.validate_url,
                    enabled=not cfg.no_url_validation,
                ),
                DiversityFilter[EcudoDataset](
                    max_similar=df_cfg.max_similar,
                    similarity_threshold=df_cfg.similarity_threshold,
                    enabled=cfg.get_diversity_filter_enabled(),
                ),
                Tap(ctx.raw_sink, transform=lambda d: d.to_json()),
                OnedataConverter[OpenAIRERecord, EcudoDataset](  # type: ignore[type-var]
                    metadata_builder=ctx.crawl_spec.metadata_builder,
                ),
                Tap(ctx.processed_sink, transform=lambda d: d.to_json()),
            ],
            rejection_sink=ctx.rejection_sink,
        )

    async def before_crawl(self, ctx: DefaultRunContext) -> None:
        """Validate that the requested organization exists."""
        ecudo_client = cast(EcudoClient, ctx.crawl_spec.client)

        with console.status("Validating organization..."):
            result = await ecudo_client.get_organizations()

        match result:
            case Ok(value=orgs):
                org = self._crawl_config.organization
                if not any(o["id"] == org for o in orgs):
                    console.error(f"Organization '{org}' not found.")
                    console.error(f"Available: {', '.join(o['id'] for o in orgs)}")
                    sys.exit(1)
            case Err(value=err):
                console.error(f"Failed to fetch organizations: {err}")
                sys.exit(1)
            case other:
                assert_never(other)

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
