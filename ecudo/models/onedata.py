"""
Onedata Dataset Model

Data structure for datasets ready for registration in Onedata.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass, field


@dataclass
class OnedataFile:
    """File information for Onedata registration."""

    name: str
    url: str
    path: str = ""

    def __post_init__(self):
        if not self.path:
            self.path = self.name


@dataclass
class OnedataDataset:
    """
    Dataset ready for registration in Onedata.

    This is the final output format expected by dataset_registrar.py.
    """

    name: str
    location: str
    pid: str
    metadata_xml: str
    files: list[OnedataFile] = field(default_factory=list)

    def to_json(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "location": self.location,
            "pid": self.pid,
            "metadata_xml": self.metadata_xml,
            "files": [
                {"name": f.name, "path": f.path, "url": f.url} for f in self.files
            ],
        }
