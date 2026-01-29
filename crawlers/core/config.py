"""Base Configuration Classes."""

# pylint: disable=too-few-public-methods

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from crawlers.core.abc.config import ConfigBase, opt


class ApiConfig(ConfigBase):
    """Base configuration for API connections."""

    base_url: str = opt(..., description="API base URL")
    timeout: int = opt(15, description="Request timeout in seconds")
    max_retries: int = opt(3, description="Maximum retry attempts")


class OutputConfig(ConfigBase):
    """Configuration for output settings."""

    output_dir: str = opt(
        "./data",
        cli=("-o", "--output-dir"),
        description="Output directory for crawled data",
    )


class ProcessingConfig(ConfigBase):
    """Configuration for parallel processing."""

    concurrency: int = opt(128, description="Number of concurrent workers")
    queue_size: int = opt(1000, description="Size of the processing queue")


class BaseCrawlConfig(ApiConfig, OutputConfig, ProcessingConfig):
    """Base configuration for inheritance and extending by crawler plugins."""
