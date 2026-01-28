"""
Ecudo Plugin Configuration.

Defines configuration classes with CLI/ENV/YAML metadata.
"""

# pylint: disable=too-few-public-methods

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from crawlers.core.config import ApiConfig, BaseCrawlConfig, ConfigBase, opt


class EcudoApiConfig(ApiConfig):
    """
    Base configuration for Ecudo API connections.

    Used by commands that only need API access (like list-orgs).
    """

    base_url: str = opt("http://central.ecudo.pl", description="Ecudo API base URL")


class URLValidatorConfig(ConfigBase):
    """Configuration for URL Validator processor."""

    enabled: bool = opt(True, yaml_key="enabled")
    invalid_url_log: str | None = opt(
        "invalid_urls.jsonl",
        yaml_key="invalid_url_log",
        description="File to log invalid URLs",
    )


class DiversityFilterConfig(ConfigBase):
    """Configuration for Diversity Filter processor."""

    enabled: bool = opt(True, yaml_key="enabled")
    max_similar: int = opt(
        10,
        yaml_key="max_similar",
        description="Maximum similar datasets allowed",
    )
    similarity_threshold: float = opt(
        0.85,
        yaml_key="similarity_threshold",
        description="Similarity threshold (0.0-1.0)",
    )


class EcudoProcessorsConfig(ConfigBase):
    """Configuration for Ecudo processors."""

    url_validator: URLValidatorConfig = opt(
        default_factory=URLValidatorConfig,
        yaml_key="url_validator",
    )
    diversity_filter: DiversityFilterConfig = opt(
        default_factory=DiversityFilterConfig,
        yaml_key="diversity_filter",
    )


class EcudoCrawlConfig(EcudoApiConfig, BaseCrawlConfig, kw_only=True):
    """
    Full configuration for Ecudo crawling.

    Combines API, output, and processing settings with crawl-specific options.
    """

    # Required positional argument
    organization: str = opt(
        ...,
        # Explicit CLI is needed for positional args to be detected correctly
        # (otherwise '--' will be prepended)
        cli="organization",
        description="Organization ID (e.g. iopan)",
    )

    # Optional crawl settings
    max_records: int | None = opt(
        None,
        cli=("-n", "--max-records"),  # Keep alias
        description="Maximum number of datasets to fetch",
    )
    page_size: int = opt(200, description="API page size for pagination")

    # CLI flags for disabling processors
    no_url_validation: bool = opt(False, description="Disable URL validation")
    no_diversity_filter: bool = opt(False, description="Disable diversity filter")

    # Nested processor configuration (YAML only)
    processors: EcudoProcessorsConfig = opt(
        default_factory=EcudoProcessorsConfig,
        # cli=False,  # Disable CLI for nested config
    )

    def __post_init__(self):
        """Validate configuration."""
        if not self.organization or self.organization.isspace():
            raise ValueError("Organization cannot be empty")

        self.organization = self.organization.strip().lower()

    def get_url_validator_enabled(self) -> bool:
        """Check if URL validator should be enabled."""
        if self.no_url_validation:
            return False
        return self.processors.url_validator.enabled  # pylint: disable=no-member

    def get_diversity_filter_enabled(self) -> bool:
        """Check if diversity filter should be enabled."""
        if self.no_diversity_filter:
            return False
        return self.processors.diversity_filter.enabled  # pylint: disable=no-member
