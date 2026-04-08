"""
Default Crawl Configuration.

Extends BaseCrawlConfig with standard options for the default pipeline:
URL validation toggle, page size, max records.
"""

# pylint: disable=too-few-public-methods

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from crawlers.core.config import ConfigBase, opt


class HttpConfig(ConfigBase):
    """Base configuration for HTTP connections."""

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


class DefaultCrawlConfig(HttpConfig, OutputConfig, ProcessingConfig, kw_only=True):
    """Default configuration for crawlers using DefaultCrawlerPlugin."""

    page_size: int = opt(100, description="Items per API page")
    max_records: int | None = opt(
        None,
        cli=("-n", "--max-records"),
        description="Maximum number of items to fetch",
    )
    no_url_validation: bool = opt(False, description="Disable URL validation")
