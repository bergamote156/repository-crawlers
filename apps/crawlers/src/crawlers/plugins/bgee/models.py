"""Bgee Data Models."""

__author__ = "Vincent Emonet"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import json
from collections.abc import Sequence
from dataclasses import dataclass, field

from rdflib import Dataset
from rdflib.term import Node

from crawlers.core import CrawlConfig, HttpConfig, opt
from crawlers.metadata.datacite import DataCiteRecord


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


@dataclass
class BgeeFile:
    """A downloadable file linked from a `BgeeDataset`.

    Satisfies both `DatasetFile` and `DataCiteFile` protocols via duck typing.
    """

    path: str
    url: str


@dataclass
class BgeeDataset:
    """Pipeline carrier for a Bgee dataset with prebuilt DataCite record."""

    identifier: str
    title: str
    files: Sequence[BgeeFile]
    metadata_record: DataCiteRecord
    _raw: BgeeRawRecord | None = field(default=None, repr=False, compare=False)

    def to_json(self) -> dict:
        """Serialize to JSON for JSONL output."""
        result: dict = {
            "identifier": self.identifier,
            "title": self.title,
            "files": [{"path": f.path, "url": f.url} for f in self.files],
        }
        if self._raw:
            try:
                result["raw_jsonld"] = json.loads(self._raw.raw)
            except (json.JSONDecodeError, ValueError):
                result["raw_jsonld"] = self._raw.raw
        return result
