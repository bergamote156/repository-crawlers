"""
Crawlers Plugins Package.

Contains specific crawler implementations.
"""

from crawlers.plugins.ecudo.plugin import EcudoPlugin

# List of all available plugins
REGISTERED_PLUGINS = [
    EcudoPlugin(),
]
