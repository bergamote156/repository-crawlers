"""Bgee Data Models."""

__author__ = "Vincent Emonet"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import json
from dataclasses import dataclass, field
from typing import Sequence

from rdflib import Dataset
from rdflib.term import Node


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

    name: str
    url: str


@dataclass
class BgeeDataset:
    """Bgee gene expression dataset.

    Satisfies both `Dataset` and `DataCiteDataset` protocols via duck typing:
    - `Dataset` protocol: identifier, title, files
    - `DataCiteDataset` protocol: identifier, title, datetime, geometry, files, self_link
    - `Serializable` protocol: to_json()
    """

    identifier: str
    title: str
    files: Sequence[BgeeFile]
    description: str | None = None
    datetime: str | None = None
    geometry: dict | None = None
    self_link: str | None = None
    keywords: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)  # DOIs/URLs from schema:citation

    _raw: BgeeRawRecord | None = field(default=None, repr=False, compare=False)

    def to_json(self) -> dict:
        """Serialize to JSON for JSONL output."""
        result: dict = {
            "identifier": self.identifier,
            "title": self.title,
            "description": self.description,
            "datetime": self.datetime,
            "self_link": self.self_link,
            "files": [{"name": f.name, "url": f.url} for f in self.files],
        }
        if self._raw:
            try:
                result["raw_jsonld"] = json.loads(self._raw.raw)
            except (json.JSONDecodeError, ValueError):
                result["raw_jsonld"] = self._raw.raw
        return result
