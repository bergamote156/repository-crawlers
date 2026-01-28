"""
Ecudo Plugin Configuration.

Defines configuration classes with CLI/ENV/YAML metadata.
"""

__author__ = "Bartosz Walkowicz"

from crawlers.core.config import ApiConfig, BaseCrawlConfig, config, opt

# --- Nested Processor Configs ---


@config
class URLValidatorConfig:
    """Configuration for URL Validator processor."""

    enabled: bool = opt(True, yaml_key="enabled")
    invalid_url_log: str | None = opt(
        "invalid_urls.jsonl",
        yaml_key="invalid_url_log",
        description="File to log invalid URLs",
    )


@config
class DiversityFilterConfig:
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


@config
class EcudoProcessorsConfig:
    """Configuration for Ecudo processors."""

    url_validator: URLValidatorConfig = opt(
        default_factory=URLValidatorConfig,
        yaml_key="url_validator",
    )
    diversity_filter: DiversityFilterConfig = opt(
        default_factory=DiversityFilterConfig,
        yaml_key="diversity_filter",
    )


# --- Main Configs ---


@config
class EcudoApiConfig(ApiConfig):
    """
    Base configuration for Ecudo API connections.

    Used by commands that only need API access (like list-orgs).
    """

    base_url: str = opt("http://central.ecudo.pl", description="Ecudo API base URL")


@config(kw_only=True)
class EcudoCrawlConfig(EcudoApiConfig, BaseCrawlConfig):
    """
    Full configuration for Ecudo crawling.

    Combines API, output, and processing settings with crawl-specific options.
    """

    # Required positional argument
    organization: str = opt(
        ...,
        # Explicit CLI is needed for positional args to be detected correctly
        # as positional by our simplistic check (no leading dash) in core/plugin.py?
        # Actually our updated core/plugin.py checks `cli_names[0].startswith("-")`.
        # If we auto-generate, it generates `--organization`.
        # So for positional args we MUST specify cli="name" explicitly still.
        cli="organization",
        description="Organization ID (e.g. iopan, p.lodz.pl)",
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
        return self.processors.url_validator.enabled

    def get_diversity_filter_enabled(self) -> bool:
        """Check if diversity filter should be enabled."""
        if self.no_diversity_filter:
            return False
        return self.processors.diversity_filter.enabled
