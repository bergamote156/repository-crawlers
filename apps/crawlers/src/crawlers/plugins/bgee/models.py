"""Bgee Data Models."""

__author__ = "Vincent Emonet"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass

from rdflib import Dataset
from rdflib.term import Node

from crawlers.core import CrawlConfig, HttpConfig, opt


class BgeeApiConfig(HttpConfig):
    """Base configuration for Bgee connections."""

    base_url: str = opt(
        "https://bgee.org/search/species",
        description="Bgee species listing page URL to start harvesting from",
    )


class BgeeCrawlConfig(BgeeApiConfig, CrawlConfig, kw_only=True):
    """Full configuration for Bgee schema.org JSON-LD crawling."""


@dataclass
class BgeeIteratorOpts:
    """Options for Bgee dataset iteration."""

    start_url: str
    max_records: int | None = None


@dataclass
class BgeeRawRecord:
    """A `schema:Dataset` node extracted from a Bgee page's JSON-LD."""

    raw: str
    """The raw JSON-LD text (combined from all scripts on the page)"""
    graph: Dataset
    """RDFLib `Dataset` with all JSON-LD from the page loaded"""
    node: Node
    """The specific `schema:Dataset` node in the graph"""
