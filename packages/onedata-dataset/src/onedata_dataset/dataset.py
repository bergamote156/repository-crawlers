"""
Onedata dataset record — final shape exchanged via JSONL between
the crawlers (producer) and the registrar (consumer).

The contract is intentionally minimal: two frozen dataclasses with a
JSON-safe `to_json()` and a matching `from_json()`. Validation
(non-empty files, unique paths, URL reachability) is a crawler-side
concern and lives outside this package.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import asdict, dataclass, field
from typing import Self


@dataclass(frozen=True)
class OnedataFile:
    """File ready for Onedata registration."""

    path: str
    url: str


@dataclass(frozen=True)
class OnedataDataset:
    """Dataset ready for Onedata registration."""

    name: str
    target_dir: str
    files: tuple[OnedataFile, ...] = field(default_factory=tuple)
    pid: str | None = None
    metadata_xml: str | None = None

    def to_json(self) -> dict:
        """Convert to JSON-safe dict for serialization."""
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict) -> Self:
        """Construct from a JSON-safe dict (mirror of `to_json`)."""
        return cls(
            name=data["name"],
            target_dir=data["target_dir"],
            files=tuple(OnedataFile(path=f["path"], url=f["url"]) for f in data["files"]),
            pid=data.get("pid"),
            metadata_xml=data.get("metadata_xml"),
        )
