"""Onedata Data Models."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import asdict, dataclass, field


@dataclass
class OnedataFile:
    """File ready for Onedata registration."""

    path: str
    url: str


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
        return asdict(self)
