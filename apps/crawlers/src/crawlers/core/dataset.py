"""
Crawler-side concerns for `OnedataDataset`: validation policy and the
failure types it can produce.

The dataset shape itself lives in the `onedata-dataset` package and is
re-exported here so plugins import from `crawlers.core.dataset`.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import asyncio
from collections import Counter
from dataclasses import dataclass

from crawlers.core.http import HttpClient, HttpFailure
from crawlers.core.result import Err, Ok, Result
from onedata_dataset import OnedataDataset, OnedataFile

__all__ = [
    "DatasetValidator",
    "DuplicatePathsFailure",
    "InvalidUrlFailure",
    "NoFilesFailure",
    "OnedataDataset",
    "OnedataFile",
    "ValidationFailure",
]

# ─────────────────────────────────────────────────────────────────────────────
# Validation failures
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NoFilesFailure:
    """Dataset had no downloadable files."""

    name: str

    def to_json(self) -> dict:
        """Serialize to a JSON-safe dict."""
        return {"type": "no_files", "name": self.name}

    def __str__(self) -> str:
        return f"{self.name}: dataset has no files"


@dataclass(frozen=True)
class DuplicatePathsFailure:
    """Two or more `OnedataFile` entries resolved to the same `path`."""

    name: str
    paths: tuple[str, ...]

    def to_json(self) -> dict:
        """Serialize to a JSON-safe dict."""
        return {"type": "duplicate_paths", "name": self.name, "paths": list(self.paths)}

    def __str__(self) -> str:
        return f"{self.name}: duplicate file paths {list(self.paths)}"


@dataclass(frozen=True)
class InvalidUrlFailure:
    """A file URL failed the registrability HEAD probe."""

    name: str
    path: str
    url: str
    failure: HttpFailure

    def to_json(self) -> dict:
        """Serialize to a JSON-safe dict."""
        return {
            "type": "invalid_url",
            "name": self.name,
            "path": self.path,
            "url": self.url,
            "failure": self.failure.to_json(),
        }

    def __str__(self) -> str:
        return f"{self.name}: unreachable file {self.path} ({self.failure})"


type ValidationFailure = NoFilesFailure | DuplicatePathsFailure | InvalidUrlFailure


# ─────────────────────────────────────────────────────────────────────────────
# Validator
# ─────────────────────────────────────────────────────────────────────────────


class DatasetValidator:
    """
    Enforces invariants the contract dataclass doesn't (non-empty files,
    unique paths) and optionally HEAD-probes file URLs for reachability.

    When `http` is None URL probing is skipped — used when the operator
    passes `--no-url-validation` or for plugins whose file URLs resolve
    to expensive dynamic queries (e.g. TopAnat).
    """

    def __init__(self, http: HttpClient | None = None):
        self._http = http

    async def validate(self, dataset: OnedataDataset) -> Result[OnedataDataset, ValidationFailure]:
        """
        Validate `dataset` and return it unchanged on success.

        Returns:
            - `Err(NoFilesFailure)` — empty file list
            - `Err(DuplicatePathsFailure)` — `OnedataFile.path` collision
            - `Err(InvalidUrlFailure)` — HEAD probe failed for some file
        """
        if not dataset.files:
            return Err(NoFilesFailure(name=dataset.pid or dataset.name))

        duplicates = sorted(p for p, c in Counter(f.path for f in dataset.files).items() if c > 1)
        if duplicates:
            return Err(
                DuplicatePathsFailure(name=dataset.pid or dataset.name, paths=tuple(duplicates))
            )

        if self._http is not None:
            checks = await asyncio.gather(*(self._http.head(f.url) for f in dataset.files))
            for file, check in zip(dataset.files, checks, strict=True):
                if isinstance(check, Err):
                    return Err(
                        InvalidUrlFailure(
                            name=dataset.pid or dataset.name,
                            path=file.path,
                            url=file.url,
                            failure=check.value,
                        )
                    )

        return Ok(dataset)
