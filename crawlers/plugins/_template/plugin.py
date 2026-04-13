"""
Example Plugin — minimal skeleton for a new crawler plugin.

Copy this directory to `crawlers/plugins/<yourname>/` and adapt
the placeholders.  The framework needs three things from you:

1. **iterate_datasets** — yield raw items from the upstream API
2. **process** — turn each raw item into an `OnedataDataset`
3. **config** — declare your CLI/YAML/ENV fields

Everything else (parallel execution, JSONL persistence, progress
display, state management) is handled by the framework.
"""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from typing import Any

from crawlers.core import (
    CrawlConfig,
    CrawlerPlugin,
    Err,
    HttpClient,
    HttpConfig,
    Result,
    RunContext,
    command,
    opt,
)
from crawlers.metadata.datacite import Creator, DataCiteRecord, IdentifierType, NameType
from crawlers.model import OnedataDataset, OnedataFile

# OpenAIRE example: `from crawlers.metadata.openaire import OpenAIRERecord`


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
#
# HttpConfig provides: base_url, timeout, max_retries
# CrawlConfig adds:    output_dir, concurrency, queue_size, max_records,
#                      no_url_validation
#
# Your ApiConfig extends HttpConfig with your API's base URL default.
# Your CrawlConfig extends both ApiConfig and CrawlConfig — Python's MRO
# merges the shared HttpConfig ancestor correctly (diamond inheritance).


# pylint: disable=too-few-public-methods
class MyApiConfig(HttpConfig):
    """Configuration for MyAPI connections (used by non-crawl commands too)."""

    base_url: str = opt("https://api.example.com/v1", description="API base URL")


# pylint: disable=too-few-public-methods
class MyCrawlConfig(MyApiConfig, CrawlConfig, kw_only=True):
    """Full crawl configuration for MyAPI."""

    # Add plugin-specific fields here as needed.
    #
    # Positional CLI arg — note explicit `cli=` for positionals:
    collection: str = opt(
        ...,
        cli="collection",
        description="Collection to crawl",
    )

    # Optional CLI flag:
    page_size: int = opt(100, description="Items per API page")


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------


class MyPlugin(CrawlerPlugin[dict, MyCrawlConfig]):
    """
    Plugin for MyAPI.

    Commands:
    - crawl:             fetch datasets from a collection
    - list-collections:  list available collections
    """

    name = "myapi"  # CLI name: `crawlers myapi crawl ...`
    description = "Crawler for MyAPI datasets"
    config_class = MyCrawlConfig

    _http: HttpClient
    _validation_http: HttpClient | None

    def run_context_name(self, config: MyCrawlConfig) -> str:
        """Appended to the run directory name (e.g. runs/2026-…_myapi_<this>/)."""
        return config.collection

    # --- Lifecycle hooks ---

    async def setup(self, ctx: RunContext[MyCrawlConfig], stack: AsyncExitStack) -> None:
        """Open HTTP clients. Store on `self`; register on `stack` for cleanup."""
        self._http = await stack.enter_async_context(HttpClient.from_config(ctx.config))
        self._validation_http = None if ctx.config.no_url_validation else self._http

    # --- Core contract ---

    async def iterate_datasets(self, ctx: RunContext[MyCrawlConfig]) -> AsyncIterator[dict]:
        """
        Yield raw items from the upstream API.

        The framework feeds these to `process()` via a bounded queue
        with `ctx.config.concurrency` parallel workers.
        """
        # Replace this loop with your API's pagination scheme.
        page = 1
        count = 0
        while True:
            result = await self._http.get_json_object(
                f"/search?page={page}&size={ctx.config.page_size}"
            )
            if isinstance(result, Err):
                raise RuntimeError(f"API error on page {page}: {result.value}")

            payload = result.value
            raw_items = payload.get("items", [])
            if not isinstance(raw_items, list) or not raw_items:
                break

            for item in raw_items:
                yield item
                count += 1
                if ctx.config.max_records and count >= ctx.config.max_records:
                    return

            page += 1

    async def process(self, raw: dict, /) -> Result[OnedataDataset, Any] | None:
        """
        Convert a raw API item into an `OnedataDataset`.

        This method may do I/O (e.g. fetch detail pages, resolve file URLs).
        It runs inside one of N concurrent workers, so keep it safe for
        parallel execution (no shared mutable state beyond `self._http`).

        Returns:
            Ok(dataset)  — persisted to processed.jsonl
            Err(failure) — persisted to rejected.jsonl (with failure details)
            None         — silently skipped (not counted as rejection)
        """
        # Map `raw` into OpenAIRE / DataCite / other `MetadataRecord` as needed.

        title = raw.get("title", "Untitled")
        pid = raw.get("doi", raw.get("id", "unknown"))

        metadata = DataCiteRecord(
            identifier=pid,
            identifier_type=IdentifierType.URL,
            creators=[Creator(name="Example creator", name_type=NameType.ORGANIZATIONAL)],
            title=title,
            publisher="Example publisher",
            publication_year=2026,
            resource_type_general="Dataset",
            resource_type_value="Research data",
        )

        files = [OnedataFile(path=f["name"], url=f["download_url"]) for f in raw.get("files", [])]

        return await OnedataDataset.build(
            pid=pid,
            name=title,
            location=title.replace("/", "-"),
            metadata=metadata,
            files=files,
            http=self._validation_http,
        )

    # --- Optional: extra commands ---

    @command
    async def list_collections(self, config: MyApiConfig, stack: AsyncExitStack) -> None:
        """List available collections."""
        http = await stack.enter_async_context(HttpClient.from_config(config))
        result = await http.get_json_object("/collections")

        if isinstance(result, Err):
            print(f"Error: {result.value}")
            return

        for coll in result.value.get("collections", []):
            print(f"  {coll['id']}  {coll['name']}")
