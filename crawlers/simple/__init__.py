"""
Simple crawler plugin framework.

A flat one-class plugin architecture: the plugin owns its HTTP/API
clients, implements `iterate_datasets` + `parse`, and returns
`OnedataDataset` directly from `parse`. The framework runs parse
in parallel workers and persists `processed.jsonl` / `rejected.jsonl`
for the registrar.

This module replaces the pipeline-based `crawlers.default` stack for
migrated plugins.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from crawlers.simple.config import SimpleCrawlConfig
from crawlers.simple.plugin import SimpleCrawlerPlugin
from crawlers.simple.workspace import SimpleRunContext

__all__ = [
    "SimpleCrawlConfig",
    "SimpleCrawlerPlugin",
    "SimpleRunContext"
]
