"""
Crawlers Plugins Package.

Contains specific crawler implementations.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from crawlers.plugins.ecudo.plugin import EcudoPlugin

# List of all available plugins
REGISTERED_PLUGINS = [
    EcudoPlugin(),
]
