"""
Registrar Data Models

Data structures for dataset registration output. Input datasets use
the shared `OnedataDataset`/`OnedataFile` contract from `onedata_dataset`.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass


@dataclass
class RegistrationResult:
    """Result of registering a single dataset."""

    dataset_name: str
    success: bool
    files_registered: int = 0
    files_skipped: int = 0
    error: str | None = None


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
