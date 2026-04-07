"""
Registrar Data Models

Data structures for dataset registration input and output.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class InputFile:
    """A file to be registered in Onedata."""

    path: str  # Relative path within dataset
    url: str  # Download URL


@dataclass
class InputDataset:
    """
    A dataset to be registered in Onedata.

    This structure matches the output format from the ecudo crawler.
    """

    name: str
    location: str  # Directory path in space (e.g., "datasets/123")
    pid: str  # Persistent identifier (DOI, etc.)
    metadata_xml: str  # OpenAIRE/DataCite XML metadata
    files: list[InputFile] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "InputDataset":
        """Create InputDataset from dictionary (e.g., from JSON)."""
        files = [
            InputFile(
                url=f.get("url", ""),
                path=f.get("path", ""),
            )
            for f in data["files"]
        ]
        return cls(
            name=data["name"],
            location=data["location"],
            pid=data["pid"],
            metadata_xml=data["metadata_xml"],
            files=files,
        )


@dataclass
class RegistrationResult:  # pylint: disable=too-many-instance-attributes
    """Result of registering a single dataset."""

    dataset_name: str
    success: bool
    files_registered: int = 0
    files_skipped: int = 0
    error: Optional[str] = None


@dataclass
class RegistrationSummary:
    """Summary of the entire registration run."""

    total_datasets: int = 0
    successful: int = 0
    failed: int = 0
    total_files_registered: int = 0
    total_files_skipped: int = 0

    def handle_result(self, result: RegistrationResult) -> None:
        """Add a registration result to the summary."""
        self.total_datasets += 1
        if result.success:
            self.successful += 1
        else:
            self.failed += 1
        self.total_files_registered += result.files_registered
        self.total_files_skipped += result.files_skipped
