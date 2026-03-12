"""Onedata Data Models."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass, field


@dataclass
class OnedataFile:
    """File ready for Onedata registration."""

    name: str
    url: str
    path: str = ""

    def __post_init__(self):
        if not self.path:
            self.path = self.name


@dataclass
class OnedataDataset:
    """
    Dataset ready for Onedata registration.

    This is the final output format of the pipeline.
    """

    name: str
    location: str
    pid: str
    metadata_xml: str
    files: list[OnedataFile] = field(default_factory=list)

    def to_json(self) -> dict:
        """Convert to JSON for serialization."""
        return {
            "name": self.name,
            "location": self.location,
            "pid": self.pid,
            "metadata_xml": self.metadata_xml,
            "files": [
                {"name": f.name, "path": f.path, "url": f.url} for f in self.files
            ],
        }
