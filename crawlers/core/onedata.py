"""Onedata data models — final shape consumed by the registrar."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import asyncio
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Self

from crawlers.core.http import HttpClient, HttpFailure
from crawlers.core.metadata import MetadataRecord
from crawlers.core.result import Err, Ok, Result


# ─────────────────────────────────────────────────────────────────────────────
# Build failures
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NoFilesFailure:
    """Dataset had no downloadable files."""

    pid: str

    def to_json(self) -> dict:
        """Serialize to a JSON-safe dict."""
        return {"type": "no_files", "pid": self.pid}

    def __str__(self) -> str:
        return f"{self.pid}: dataset has no files"


@dataclass(frozen=True)
class DuplicatePathsFailure:
    """Two or more `OnedataFile` entries resolved to the same `path`."""

    pid: str
    paths: tuple[str, ...]

    def to_json(self) -> dict:
        """Serialize to a JSON-safe dict."""
        return {"type": "duplicate_paths", "pid": self.pid, "paths": list(self.paths)}

    def __str__(self) -> str:
        return f"{self.pid}: duplicate file paths {list(self.paths)}"


@dataclass(frozen=True)
class InvalidUrlFailure:
    """A file URL failed the registrability HEAD probe."""

    pid: str
    path: str
    url: str
    failure: HttpFailure

    def to_json(self) -> dict:
        """Serialize to a JSON-safe dict."""
        return {
            "type": "invalid_url",
            "pid": self.pid,
            "path": self.path,
            "url": self.url,
            "failure": self.failure.to_json(),
        }

    def __str__(self) -> str:
        return f"{self.pid}: unreachable file {self.path} ({self.failure})"


type BuildFailure = NoFilesFailure | DuplicatePathsFailure | InvalidUrlFailure


# ─────────────────────────────────────────────────────────────────────────────
# Dataset
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OnedataFile:
    """File ready for Onedata registration."""

    path: str
    url: str


@dataclass(frozen=True)
class OnedataDataset:
    """
    Dataset ready for Onedata registration.

    Build instances via `OnedataDataset.build(...)` so the validation policy
    (non-empty files, unique paths, optional URL reachability) and the eager
    XML materialization are applied uniformly.
    """

    name: str
    location: str
    pid: str
    metadata_xml: str
    files: tuple[OnedataFile, ...] = field(default_factory=tuple)

    # pylint: disable=too-many-arguments
    @classmethod
    async def build(
        cls,
        *,
        pid: str,
        name: str,
        location: str,
        metadata: MetadataRecord,
        files: Sequence[OnedataFile],
        http: HttpClient | None = None,
    ) -> Result[Self, BuildFailure]:
        """
        Validate inputs and produce a registrar-ready `OnedataDataset`.

        The metadata XML is materialized eagerly via `metadata.to_xml()` so
        the returned dataset carries no references to the source parser
        state. When `http` is provided, file URLs are probed in parallel
        with HEAD requests; otherwise reachability is not checked.

        Returns:
            - `Err(NoFilesFailure)` — empty file list
            - `Err(DuplicatePathsFailure)` — `OnedataFile.path` collision
            - `Err(InvalidUrlFailure)` — HEAD probe failed for some file
        """
        if not files:
            return Err(NoFilesFailure(pid=pid))

        duplicates = sorted(
            p for p, c in Counter(f.path for f in files).items() if c > 1
        )
        if duplicates:
            return Err(DuplicatePathsFailure(pid=pid, paths=tuple(duplicates)))

        if http is not None:
            checks = await asyncio.gather(
                *(_check_file_registrable(http, f.url) for f in files)
            )
            for file, check in zip(files, checks, strict=True):
                if isinstance(check, Err):
                    return Err(
                        InvalidUrlFailure(
                            pid=pid,
                            path=file.path,
                            url=file.url,
                            failure=check.value,
                        )
                    )

        return Ok(
            cls(
                name=name,
                location=location,
                pid=pid,
                metadata_xml=metadata.to_xml(),
                files=tuple(files),
            )
        )

    def to_json(self) -> dict:
        """Convert to JSON-safe dict for serialization."""
        return asdict(self)


async def _check_file_registrable(
    http: HttpClient, url: str
) -> Result[None, HttpFailure]:
    """Onedata's registrability policy: a file URL is OK if HEAD returns 200."""
    return await http.head(url)
