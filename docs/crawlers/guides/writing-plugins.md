---
title: Writing Plugins
description: >
  Step-by-step guide to creating a new crawler plugin — API client,
  parser, configuration, plugin class, and registration. Includes
  examples from the built-in plugins and covers custom pipelines,
  commands, and validation hooks.
topic: crawlers/guides/writing-plugins
audience: external-plugin-author
generated: 2026-04-01
last_reviewed: 2026-04-04
source_modules:
  - crawlers/default/plugin.py
  - crawlers/default/config.py
  - crawlers/default/crawl_spec.py
  - crawlers/plugins/ecudo/plugin.py
  - crawlers/plugins/ecudo/config.py
  - crawlers/plugins/ecudo/api.py
  - crawlers/plugins/ecudo/parser.py
  - crawlers/plugins/eodc/plugin.py
  - crawlers/plugins/eodc/config.py
  - crawlers/plugins/eodc/api.py
  - crawlers/plugins/eodc/parser.py
  - crawlers/plugins/__init__.py
source_commits:
  public-data-crawlers: bbd9be2e7
status: draft
---

# Writing Plugins

By the end of this guide, you'll have a working crawler that fetches
from your API and produces Onedata-ready records — runnable as
`crawlers myapi crawl <collection>`.

## Overview

A plugin crawls datasets from an external API and produces
Onedata-ready records. The minimal set of components:

1. **API client** — fetches data from the external service.
2. **Parser** — transforms raw API responses into a dataset model.
3. **Config** — declares CLI arguments, YAML keys, and defaults.
4. **Plugin class** — ties everything together by implementing
   `prepare_crawl()`.
5. **Registration** — adds the plugin to `REGISTERED_PLUGINS`.

Optionally, you may also provide:
- A custom **metadata builder** if the standard DataCite/OpenAIRE
  builders need adaptation.
- A custom **pipeline** if you need extra processing stages.
- Additional **commands** beyond the auto-registered `crawl`.

## Plugin Directory Structure

Place your plugin under `crawlers/plugins/<name>/`:

```
crawlers/plugins/myapi/
  __init__.py      # Empty or re-exports
  api.py           # ApiClient subclass
  parser.py        # Parser + dataset model
  config.py        # Config classes
  plugin.py        # Plugin class
  metadata.py      # (optional) Custom MetadataBuilder
```

## Step 1: Dataset Model and Parser

> [!TIP]
> **Source:** `crawlers/processors/parsers.py:20-42`

Define a dataclass for your parsed dataset. You'll need to choose
between DataCite and OpenAIRE metadata — pick the one that matches
your target standard. Your dataset model must satisfy the protocol of
whichever builder you choose — see the
[DataCite protocol](../arch/metadata.md#dataset-protocol) or
[OpenAIRE protocol](../arch/metadata.md#dataset-protocol-1) class
diagrams for the required attributes.

```python
@dataclass
class MyDataset:
    identifier: str
    title: str
    description: str
    publisher: str
    issued: str
    files: list[MyFile]
    language: str
    keywords: list[str]
    access_level: str
    spatial: str | None
    temporal: str | None
    _raw: dict  # Keep raw data for debugging

    def to_json(self) -> dict:
        """Serialize for JSONL sinks."""
        return self._raw
```

Then implement a parser. The `Parser` protocol requires a single
method:

```python
class MyParser:
    def parse(self, raw: dict) -> MyDataset | None:
        """Parse raw API response. Return None to skip."""
        ...
```

Return `None` to silently skip unparseable items. Raise exceptions
for unexpected failures.

## Step 2: API Client

> [!TIP]
> **Source:** `crawlers/core/api.py:56-229`

Subclass `ApiClient` with your API's iterator options type and the
type yielded by the iterator:

```python
from dataclasses import dataclass
from collections.abc import AsyncIterator

from crawlers.core.api import ApiClient
from crawlers.core.result import Ok, Err
```

```python
@dataclass
class MyIteratorOpts:
    collection: str
    page_size: int = 100
    max_items: int | None = None

class MyClient(ApiClient[MyIteratorOpts, dict]):
    async def iterate_datasets(
        self, opts: MyIteratorOpts
    ) -> AsyncIterator[dict]:
        """Paginate through the API and yield raw items."""
        page = 1
        count = 0
        while True:
            url = f"{self.base_url}/search?page={page}&size={opts.page_size}"
            result = await self.get_json(url)

            match result:
                case Ok(value=data):
                    items = data.get("items", [])
                    if not items:
                        break
                    for item in items:
                        yield item
                        count += 1
                        if opts.max_items and count >= opts.max_items:
                            return
                    page += 1
                case Err(value=err):
                    console.error(f"API error: {err}")
                    break
```

The base class gives you `get_json()`, `post_json()`, and
`validate_url()` — all with automatic retries and exponential
backoff.

**Choose the iterator yield type based on your API:**
- If the API returns full items in listing calls, yield `dict` and
  use `ParserProcessor` in the pipeline (like EODC).
- If the API returns IDs that need a separate detail fetch, yield
  `str` and use `DatasetResolver` in the pipeline (like Ecudo).

## Step 3: Configuration

> [!TIP]
> **Source:** `crawlers/default/config.py:17-52`

Build your config by composing base classes. The simplest approach
extends `DefaultCrawlConfig` (which includes API, output, and
processing settings):

```python
class MyApiConfig(ApiConfig):
    """Used by non-crawl commands (e.g. list-collections)."""
    base_url: str = opt("https://api.example.com", description="API base URL")

class MyCrawlConfig(MyApiConfig, DefaultCrawlConfig, kw_only=True):
    """Full crawl configuration."""
    collection: str = opt(..., cli="collection", description="Collection to crawl")
    datetime_range: str | None = opt(
        None,
        cli=("--datetime", "-d"),
        description="ISO datetime range",
    )
```

For fields that are too detailed for CLI but useful in YAML, use
nested configs:

```python
class FilterConfig(ConfigBase):
    enabled: bool = opt(True, yaml_key="enabled")
    threshold: float = opt(0.85, yaml_key="threshold")

class MyCrawlConfig(MyApiConfig, DefaultCrawlConfig, kw_only=True):
    collection: str = opt(..., cli="collection")
    my_filter: FilterConfig = opt(
        default_factory=FilterConfig,
        yaml_key="my_filter",
    )
```

See [Configuration](../arch/configuration.md) for full details on
`opt()`, resolution priority, and YAML structure.

## Step 4: Plugin Class

> [!TIP]
> **Source:** `crawlers/default/plugin.py:41-93` · `crawlers/default/crawl_spec.py:16-50`

The minimal plugin subclasses `DefaultCrawlerPlugin` and implements
`prepare_crawl()`:

```python
class MyPlugin(DefaultCrawlerPlugin):
    name = "myapi"
    description = "Crawler for My API"
    config_class = MyCrawlConfig

    def prepare_crawl(self, config: DefaultCrawlConfig) -> DefaultCrawlSpec:
        # The base class declares the generic signature; cast to your
        # config type since Python doesn't support covariant overrides.
        cfg = cast(MyCrawlConfig, config)
        return DefaultCrawlSpec(
            client=MyClient(
                base_url=cfg.base_url,
                timeout=cfg.timeout,
                max_retries=cfg.max_retries,
            ),
            iterator_opts=MyIteratorOpts(
                collection=cfg.collection,
                page_size=cfg.page_size,
                max_items=cfg.max_records,
            ),
            parser=MyParser(),
            metadata_builder=OpenAIREBuilder(),  # or DataCiteBuilder subclass
            run_context_name=cfg.collection,
            banner_subtitle=f"Collection: {cfg.collection}",
        )
```

Setting `name` as a string triggers auto-registration of the
`"crawl"` command. The framework handles client lifecycle, pipeline
construction, parallel execution, state persistence, and display.

## Step 5: Register the Plugin

Add your plugin to `crawlers/plugins/__init__.py`:

> [!TIP]
> **Source:** `crawlers/plugins/__init__.py:11-23`

```python
from crawlers.plugins.myapi.plugin import MyPlugin

REGISTERED_PLUGINS = [
    EcudoPlugin(),
    EODCPlugin(),
    BgeePlugin(),
    VipPlugin(),
    MyPlugin(),       # <-- add here
]
```

Your plugin is now available as `crawlers myapi crawl ...`.

## Step 6: Verify

Run `--help` to confirm your plugin is registered and your config
fields appear:

```bash
crawlers myapi crawl --help
```

Then run a small test crawl to verify the pipeline works end-to-end:

```bash
crawlers myapi crawl my-collection --max-records 5
```

Check the run directory for `processed.jsonl` (your Onedata records)
and `rejected.jsonl` (any failed items with reasons). A correct
record in `processed.jsonl` looks like:

```json
{"name": "Dataset Title", "location": "/collection/dataset-title", "pid": "doi:10.1234/example", "metadata": "<resource xmlns=...>...</resource>", "files": [{"url": "https://...", "path": "data.csv"}]}
```

Each line is a self-contained JSON object with `name`, `location`,
`pid`, `metadata` (XML string), and `files`.

## Custom Pipeline

The default pipeline inspects `spec.resolve_fn` to choose between
`DatasetResolver` (when set) and `ParserProcessor` (when `None`).
For most APIs, setting `resolve_fn` in `DefaultCrawlSpec` is
sufficient — no override needed.

Override `build_pipeline()` when you need extra processing stages
or a different processor order. Note that there is no
`pipeline.insert()` — you must rebuild the full chain. Ecudo does
this to add a `DiversityFilter`:

> [!TIP]
> **Source:** `crawlers/default/plugin.py:179-209`

```python
def build_pipeline(self, ctx: DefaultRunContext) -> ProcessorPipeline:
    spec = ctx.crawl_spec
    return ProcessorPipeline(
        processors=[
            DatasetResolver(
                resolve_fn=cast(MyClient, spec.client).get_item,
                parser=spec.parser,
            ),
            URLValidator(
                validate_fn=spec.client.validate_url,
                enabled=not ctx.config.no_url_validation,
            ),
            DiversityFilter(max_similar=10, similarity_threshold=0.85),
            Tap(ctx.raw_sink, transform=lambda d: d.to_json()),
            OnedataConverter(metadata_builder=spec.metadata_builder),
            Tap(ctx.processed_sink, transform=lambda d: d.to_json()),
        ],
        rejection_sink=ctx.rejection_sink,
    )
```

If you do not override `build_pipeline()`, the default pipeline is:
```
ParserProcessor/DatasetResolver → URLValidator → Tap(raw) → OnedataConverter → Tap(processed)
```
(The first processor depends on whether `resolve_fn` is set in the spec.)

## Custom Commands

Add extra commands with the `@command()` decorator. Each command
gets its own config class (which can be simpler than the crawl
config):

```python
@command("list-collections", MyApiConfig, help="List available collections")
async def list_collections(self, config: MyApiConfig) -> None:
    async with MyClient(
        base_url=config.base_url,
        timeout=config.timeout,
        max_retries=config.max_retries,
    ) as client:
        result = await client.get_collections()
        # Display results...
```

This registers as `crawlers myapi list-collections`.

## Validation Hooks

> [!TIP]
> **Source:** `crawlers/default/plugin.py:110-117`

Override `before_crawl()` to validate preconditions after the client
session is open. Ecudo uses this to verify the requested
organization exists:

```python
async def before_crawl(self, ctx: DefaultRunContext) -> None:
    client = cast(MyClient, ctx.crawl_spec.client)
    result = await client.validate_collection(self._collection)
    if isinstance(result, Err):
        console.error(f"Collection not found: {self._collection}")
        sys.exit(1)
```

> [!NOTE]
> `sys.exit(1)` is the current convention for validation failures
> in `before_crawl()` — the framework does not yet provide a
> structured way to abort a crawl before the pipeline starts.

Override `after_crawl()` for post-crawl actions (cleanup, summary
reporting, etc.).

## Custom Metadata Builder

If the standard DataCite/OpenAIRE builders need adaptation, subclass
the appropriate builder and override what you need:

```python
class MyDataCiteBuilder(DataCiteBuilder["MyDataset"]):
    creator_name = "My Organization"
    publisher_name = "My Publisher"
    default_subjects = ["Earth Science", "Remote Sensing"]

    def build_descriptions_section(self, root, ctx):
        # Custom description logic
        ...
```

For adding entirely new sections, override `get_sections()`:

```python
def get_sections(self):
    sections = super().get_sections()
    sections.append(self.build_custom_section)
    return sections
```

See [Metadata — Extending](../arch/metadata.md#extending-metadata-builders)
for the full extension point reference.

## Real Examples

Use this decision tree to pick the right reference plugin:

- **API returns full items in listing calls?** → Follow **EODC**.
  Uses the default pipeline with `ParserProcessor`, no
  `build_pipeline()` override needed.
- **API returns IDs that need a separate detail fetch?** → Follow
  **Ecudo**. Sets `resolve_fn` in spec for `DatasetResolver`
  behavior.
- **Need deduplication of near-identical datasets?** → Look at
  Ecudo's `DiversityFilter` and `DiversityFilterConfig`.
- **Need custom metadata defaults?** → Look at EODC's
  `EODCDataCiteBuilder` (subclasses `DataCiteBuilder` with
  Sentinel-1 specific values).

**EODC** (`crawlers/plugins/eodc/`) — the simpler pattern:
- STAC API returns full items → default pipeline with
  `ParserProcessor`.
- Custom `DataCiteBuilder` subclass for Sentinel-1 metadata
  defaults.
- `list-collections` extra command.

**Ecudo** (`crawlers/plugins/ecudo/`) — the advanced pattern:
- API returns IDs → overrides `build_pipeline()` to add
  `DiversityFilter`.
- Nested `DiversityFilterConfig` for YAML-only tuning.
- `before_crawl()` validates organization exists.
- `list-orgs` extra command.

**Bgee** and **VIP** both use the default pipeline pattern (like
EODC) — `ParserProcessor` with no `build_pipeline()` override. VIP
additionally demonstrates a multi-step parser that combines
metadata from several API endpoints.

