"""
EODC Plugin Configuration.

Defines configuration classes with CLI/ENV/YAML metadata.
"""

# pylint: disable=too-few-public-methods

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from crawlers.core.config import ApiConfig, BaseCrawlConfig, ConfigBase, opt


class EODCApiConfig(ApiConfig):
    """
    Base configuration for EODC STAC API connections.

    Used by commands that only need API access (like list-collections).
    """

    base_url: str = opt(
        "https://stac.eodc.eu/api/v1",
        description="EODC STAC API base URL",
    )


class URLValidatorConfig(ConfigBase):
    """Configuration for URL Validator processor."""

    enabled: bool = opt(True, yaml_key="enabled")
    invalid_url_log: str | None = opt(
        "invalid_urls.jsonl",
        yaml_key="invalid_url_log",
        description="File to log invalid URLs",
    )


class EODCProcessorsConfig(ConfigBase):
    """Configuration for EODC processors."""

    url_validator: URLValidatorConfig = opt(
        default_factory=URLValidatorConfig,
        yaml_key="url_validator",
    )


class EODCCrawlConfig(EODCApiConfig, BaseCrawlConfig, kw_only=True):
    """
    Full configuration for EODC STAC crawling.

    Combines API, output, and processing settings with crawl-specific options.
    """

    # Required: collections to crawl
    collections: str = opt(
        ...,
        cli="collections",
        description="STAC collections to crawl (comma-separated, e.g. SENTINEL1_GRD)",
    )

    # Optional spatial filter (YAML only - GeoJSON is complex for CLI)
    intersects: dict | None = opt(
        None,
        cli=False,  # Disable CLI for complex GeoJSON
        yaml_key="intersects",
        description="GeoJSON geometry for spatial filter",
    )

    # Optional temporal filter
    datetime_range: str | None = opt(
        None,
        cli=("--datetime", "-d"),
        description="ISO datetime range (e.g. 2025-01-01/2025-01-31)",
    )

    # Pagination settings
    page_size: int = opt(100, description="Items per API page")
    max_records: int | None = opt(
        None,
        cli=("-n", "--max-records"),
        description="Maximum number of items to fetch",
    )

    # CLI flags for disabling processors
    no_url_validation: bool = opt(False, description="Disable URL validation")

    # Nested processor configuration (YAML only)
    processors: EODCProcessorsConfig = opt(
        default_factory=EODCProcessorsConfig,
    )

    def __post_init__(self):
        """Validate and transform configuration."""
        if not self.collections or self.collections.isspace():
            raise ValueError("Collections cannot be empty")

        self.collections = self.collections.strip()

    def get_collections_list(self) -> list[str]:
        """Get collections as a list."""
        return [c.strip() for c in self.collections.split(",") if c.strip()]

    def get_url_validator_enabled(self) -> bool:
        """Check if URL validator should be enabled."""
        if self.no_url_validation:
            return False
        return self.processors.url_validator.enabled  # pylint: disable=no-member
