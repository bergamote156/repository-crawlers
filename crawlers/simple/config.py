"""
Simple crawl configuration.

Minimal base config for `SimpleCrawlerPlugin`: API settings,
output directory, concurrency, max_records, URL validation toggle.
Plugins extend this with their own fields (credentials, selectors).
"""

# pylint: disable=too-few-public-methods

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from crawlers.core.config import opt
from crawlers.default.config import HttpConfig, OutputConfig, ProcessingConfig


class SimpleCrawlConfig(HttpConfig, OutputConfig, ProcessingConfig, kw_only=True):
    """
    Base configuration for crawlers using `SimpleCrawlerPlugin`.

    Bundles the settings every simple plugin needs: API connection
    parameters (for `HttpClient.from_config`), output directory,
    worker pool sizing, record cap, and URL validation toggle.
    """

    max_records: int | None = opt(
        None,
        cli=("-n", "--max-records"),
        description="Maximum number of items to fetch",
    )
    no_url_validation: bool = opt(
        False,
        description="Disable HEAD-probe URL validation during parse",
    )
