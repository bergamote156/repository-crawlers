"""
TopAnat Plugin.

Crawler plugin for the curated GWAS Catalog entries used by the TopAnat
Galaxy workflow. Iterates a small seed list (EFO/MONDO traits + PubMed
publications) and registers each one as an Onedata dataset whose two
"files" are import-by-reference URLs to the GWAS associations API
(JSON + TSV).
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from rich.table import Table

from crawlers.core import (
    CrawlerPlugin,
    Err,
    HttpClient,
    HttpFailure,
    Ok,
    ResponseFailure,
    Result,
    RunContext,
    TimeoutFailure,
    command,
)
from crawlers.model.dataset import OnedataDataset, OnedataFile
from crawlers.plugins.topanat.api import PublicationInfo, TopanatClient, TraitInfo
from crawlers.plugins.topanat.models import (
    TopanatCrawlConfig,
    TopanatEntry,
    TopanatSeedsConfig,
)
from crawlers.plugins.topanat.parser import (
    build_publication_record,
    build_trait_record,
)
from crawlers.ui import console

# ─────────────────────────────────────────────────────────────────────────────
# Failure type — for entries whose upstream metadata fetch fails
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TopanatFetchFailure:
    """Upstream GWAS metadata fetch failed for a seeded entry."""

    pid: str
    failure: HttpFailure

    def to_json(self) -> dict:
        """Serialize to a JSON-safe dict."""
        return {
            "type": "topanat_fetch_failure",
            "pid": self.pid,
            "failure": self.failure.to_json(),
        }

    def __str__(self) -> str:
        return f"{self.pid}: failed to fetch GWAS metadata ({self.failure})"


# ─────────────────────────────────────────────────────────────────────────────
# Plugin
# ─────────────────────────────────────────────────────────────────────────────


class TopanatPlugin(CrawlerPlugin[TopanatEntry, TopanatCrawlConfig]):
    """Crawler for curated GWAS Catalog entries (TopAnat workflow)."""

    name = "topanat"
    description = "Crawler for curated GWAS Catalog traits and publications (TopAnat workflow)"

    config_class = TopanatCrawlConfig

    _client: TopanatClient
    _validation_http: HttpClient | None

    # --- Lifecycle ---

    async def setup(self, ctx: RunContext[TopanatCrawlConfig], stack: AsyncExitStack) -> None:
        """Open a shared `HttpClient` and build the API façade."""
        http = await stack.enter_async_context(HttpClient.from_config(ctx.config))
        self._client = TopanatClient(http)
        self._validation_http = None if ctx.config.no_url_validation else http

    # --- Iteration & parse ---

    async def iterate_datasets(
        self, ctx: RunContext[TopanatCrawlConfig]
    ) -> AsyncIterator[TopanatEntry]:
        """Yield seeded entries from the configured YAML file."""
        entries = _load_seeds(Path(ctx.config.seeds))
        console.info(f"Loaded {len(entries)} seeded entries from {ctx.config.seeds}")
        for entry in entries:
            yield entry

    async def process(self, entry: TopanatEntry, /) -> Result[OnedataDataset, Any] | None:
        """Fetch upstream metadata, build DataCite record, assemble OnedataDataset."""
        fetch_result: Ok[PublicationInfo] | Ok[TraitInfo] | Err[ResponseFailure | TimeoutFailure]
        if entry.kind == "trait":
            fetch_result = await self._client.fetch_trait(entry.id)
            if isinstance(fetch_result, Err):
                return Err(TopanatFetchFailure(pid=entry.id, failure=fetch_result.value))
            parsed = build_trait_record(fetch_result.value)
        else:
            fetch_result = await self._client.fetch_publication(entry.id)
            if isinstance(fetch_result, Err):
                return Err(TopanatFetchFailure(pid=entry.id, failure=fetch_result.value))
            parsed = build_publication_record(fetch_result.value)

        files = [
            OnedataFile(path="data.json", url=parsed.json_url),
            # OnedataFile(path="data.tsv", url=parsed.tsv_url),  # TODO
        ]

        return await OnedataDataset.build(
            pid=parsed.identifier,
            name=parsed.title,
            location=parsed.title.replace("/", "-"),
            metadata=parsed.metadata,
            files=files,
            http=self._validation_http,
        )

    # --- Auxiliary commands ---

    @command
    async def list_seeds(self, config: TopanatSeedsConfig, _stack: AsyncExitStack) -> None:
        """Print the seeded entries that would be crawled."""
        entries = _load_seeds(Path(config.seeds))

        table = Table(
            title=f"TopAnat seeds ({len(entries)})",
            show_header=True,
            header_style="bold",
        )
        table.add_column("Kind", style="cyan")
        table.add_column("ID", style="green")
        for entry in entries:
            table.add_row(entry.kind, entry.id)

        console.print(table)


# ─────────────────────────────────────────────────────────────────────────────
# Seed loading
# ─────────────────────────────────────────────────────────────────────────────


def _load_seeds(path: Path) -> list[TopanatEntry]:
    """Parse the seeds YAML into a list of `TopanatEntry`."""
    if not path.exists():
        raise FileNotFoundError(f"Seeds file not found: {path}")

    data = yaml.safe_load(path.read_text()) or {}
    raw_entries = data.get("entries", [])
    if not isinstance(raw_entries, list):
        raise ValueError(f"Seeds file {path} must contain a top-level 'entries' list")

    parsed: list[TopanatEntry] = []
    for i, raw in enumerate(raw_entries):
        if not isinstance(raw, dict):
            raise ValueError(f"Seed #{i} in {path} is not a mapping: {raw!r}")
        kind = raw.get("kind")
        ident = raw.get("id")
        if kind not in ("trait", "publication"):
            raise ValueError(
                f"Seed #{i} in {path}: kind must be 'trait' or 'publication', got {kind!r}"
            )
        if not ident:
            raise ValueError(f"Seed #{i} in {path}: missing 'id'")
        parsed.append(TopanatEntry(kind=kind, id=str(ident)))

    return parsed
