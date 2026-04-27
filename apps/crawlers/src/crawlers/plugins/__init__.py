"""
Crawlers Plugins Package.

Contains specific crawler implementations.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from typing import Any

from crawlers.core import CrawlerPlugin
from crawlers.plugins.bgee.plugin import BgeePlugin
from crawlers.plugins.ecudo.plugin import EcudoPlugin
from crawlers.plugins.eodc.plugin import EODCPlugin
from crawlers.plugins.topanat.plugin import TopanatPlugin
from crawlers.plugins.vip.plugin import VipPlugin

# List of all available plugins
REGISTERED_PLUGINS: list[CrawlerPlugin[Any, Any]] = [
    EcudoPlugin(),
    EODCPlugin(),
    BgeePlugin(),
    VipPlugin(),
    TopanatPlugin(),
]
