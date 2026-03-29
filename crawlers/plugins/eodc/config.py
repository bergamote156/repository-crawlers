"""EODC Plugin Configuration (default architecture)."""

# pylint: disable=too-few-public-methods

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from crawlers.core.default.config import ApiConfig, DefaultCrawlConfig, opt


class EODCApiConfig(ApiConfig):
    """
    Base configuration for EODC API connections.

    Used by commands that only need API access (like list-orgs).
    """

    base_url: str = opt(
        "https://stac.eodc.eu/api/v1",
        description="EODC STAC API base URL",
    )


class EODCCrawlConfig(EODCApiConfig, DefaultCrawlConfig, kw_only=True):
    """Configuration for EODC STAC crawling."""

    collections: str = opt(
        ...,
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

    def __post_init__(self):
        if not self.collections or self.collections.isspace():
            raise ValueError("Collections cannot be empty")

        self.collections = self.collections.strip()

    def get_collections_list(self) -> list[str]:
        """Return collections as a list of stripped strings."""
        return [c.strip() for c in self.collections.split(",") if c.strip()]
