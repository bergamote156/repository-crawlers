"""Bgee Plugin Configuration."""

# pylint: disable=too-few-public-methods

__author__ = "Vincent Emonet"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from crawlers.core.config import ApiConfig, BaseCrawlConfig, opt


class BgeeApiConfig(ApiConfig):
    """Base configuration for Bgee connections."""

    base_url: str = opt(
        "https://bgee.org/search/species",
        description="Bgee species listing page URL to start harvesting from",
    )


class BgeeCrawlConfig(BgeeApiConfig, BaseCrawlConfig, kw_only=True):
    """Full configuration for Bgee schema.org JSON-LD crawling."""

    max_records: int | None = opt(
        None,
        cli=("-n", "--max-records"),
        description="Maximum number of datasets to fetch",
    )
