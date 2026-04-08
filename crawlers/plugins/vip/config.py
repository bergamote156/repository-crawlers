"""VIP Plugin Configuration."""

# pylint: disable=too-few-public-methods

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from crawlers.default.config import DefaultCrawlConfig, HttpConfig, opt


class VipApiConfig(HttpConfig):
    """Base configuration for VIP Girder API connections."""

    base_url: str = opt(
        "https://srmnopt.creatis.insa-lyon.fr/api/v1",
        description="VIP Girder REST API base URL",
    )


class VipCrawlConfig(VipApiConfig, DefaultCrawlConfig, kw_only=True):
    """Configuration for VIP Girder collection crawling."""

    collection: str = opt(
        ...,
        cli="collection",
        description="Name of the VIP collection to crawl",
    )

    def __post_init__(self):
        if not self.collection or self.collection.isspace():
            raise ValueError("Collection name cannot be empty")

        self.collection = self.collection.strip()
