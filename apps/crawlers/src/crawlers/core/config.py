"""
Crawl configuration.

Base config classes for `CrawlerPlugin`: HTTP settings, output directory,
concurrency, record cap, URL validation toggle.  Plugin-specific configs
extend `CrawlConfig` with their own fields.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from typing import Annotated

from confline import CliAlias, ConfigBase, opt


class HttpConfig(ConfigBase):
    """Base configuration for HTTP connections."""

    base_url: str = opt(description="API base URL")
    timeout: int = opt(15, description="Request timeout in seconds")
    max_retries: int = opt(3, description="Maximum retry attempts")


class OutputConfig(ConfigBase):
    """Configuration for output settings."""

    output_dir: Annotated[str, CliAlias("-o", "--output-dir")] = opt(
        "./data",
        description="Output directory for crawled data",
    )


class ProcessingConfig(ConfigBase):
    """Configuration for parallel processing."""

    concurrency: int = opt(128, description="Number of concurrent workers")
    queue_size: int = opt(1000, description="Size of the processing queue")


class CrawlConfig(HttpConfig, OutputConfig, ProcessingConfig, kw_only=True):
    """Base configuration for `CrawlerPlugin`.

    Plugin-specific configs use diamond inheritance to combine a custom
    `HttpConfig` subclass (with their own `base_url` default) and `CrawlConfig`:

        class MyApiConfig(HttpConfig):
            base_url: str = opt("https://my.api", ...)

        class MyCrawlConfig(MyApiConfig, CrawlConfig, kw_only=True):
            ...

    Python's MRO resolves the shared `HttpConfig` ancestor correctly —
    each field is initialized exactly once. Always pass `kw_only=True`
    on the leaf class to avoid ordering conflicts between required and
    defaulted fields.
    """

    max_records: Annotated[int | None, CliAlias("-n", "--max-records")] = opt(
        None,
        description="Maximum number of items to fetch",
    )
    no_url_validation: bool = opt(
        False,
        description="Disable HEAD-probe URL validation before persistence",
    )
