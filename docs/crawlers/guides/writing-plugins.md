---
title: Writing Plugins
description: >
  Step-by-step guide to creating a new crawler plugin — configuration,
  lifecycle hooks, iteration, processing, and registration.
topic: crawlers/guides/writing-plugins
audience: external-plugin-author
generated: 2026-04-01
last_reviewed: 2026-04-09
source_modules:
  - apps/crawlers/src/crawlers/core/plugin.py
  - apps/crawlers/src/crawlers/core/config.py
  - apps/crawlers/src/crawlers/core/crawl_config.py
  - apps/crawlers/src/crawlers/core/http.py
  - apps/crawlers/src/crawlers/plugins/ecudo/plugin.py
  - apps/crawlers/src/crawlers/plugins/eodc/plugin.py
  - apps/crawlers/src/crawlers/plugins/_template/plugin.py
  - apps/crawlers/src/crawlers/plugins/__init__.py
status: draft
---

# Writing Plugins

By the end of this guide you'll have a working crawler runnable as
`crawlers myapi crawl <collection>`.

> A complete, copy-pasteable skeleton lives in
> `apps/crawlers/src/crawlers/plugins/_template/plugin.py`.

## What you need to implement

A plugin extends `CrawlerPlugin[RawT, ConfigT]` and provides:

1. **`iterate_datasets(ctx)`** — async generator yielding raw items
   from the upstream API.
2. **`process(raw)`** — turns each raw item into a
   `Result[OnedataDataset, failure]` (or `None` to skip).
3. **Config class** — declares your CLI arguments, YAML keys, and
   defaults by extending `CrawlConfig`.

The framework handles everything else: parallel worker pool, JSONL
persistence, progress display, run directories, state management.

## Plugin directory structure

```
apps/crawlers/src/crawlers/plugins/myapi/
  __init__.py      # empty
  plugin.py        # plugin class + config
  api.py           # (optional) API client facade
  parser.py        # (optional) raw → metadata mapping
```

Config classes can live in `plugin.py` (simple plugins) or in a
separate `config.py` (if configs get large).

## Step 1: Configuration

```python
from crawlers.core import CrawlConfig, HttpConfig, opt

class MyApiConfig(HttpConfig):
    """Base HTTP config — also used by non-crawl commands."""
    base_url: str = opt("https://api.example.com/v1", description="API base URL")

class MyCrawlConfig(MyApiConfig, CrawlConfig, kw_only=True):
    """Full crawl config."""
    collection: str = opt(..., cli="collection", description="Collection to crawl")
    page_size: int = opt(100, description="Items per API page")
```

**How it works:**

- `HttpConfig` provides `base_url`, `timeout`, `max_retries`.
- `CrawlConfig` adds `output_dir`, `concurrency`, `queue_size`,
  `max_records`, `no_url_validation`.
- Your `MyCrawlConfig` extends both via `MyApiConfig` and
  `CrawlConfig`. Python's MRO merges the shared `HttpConfig`
  ancestor correctly (diamond inheritance).
- Each `opt()` field auto-generates CLI flags, YAML keys, and ENV
  variables. Use `cli=False`, `env=False`, or `yaml_key=False` to
  disable specific sources.
- Resolution priority: **CLI > YAML (command) > YAML (plugin) >
  YAML (global) > ENV > default**.
- For positional CLI args, set `cli="argname"` (no dashes).

## Step 2: Plugin class

```python
from crawlers.core import CrawlerPlugin, HttpClient, Result, Err, RunContext
from crawlers.model import OnedataDataset, OnedataFile

class MyPlugin(CrawlerPlugin[dict, MyCrawlConfig]):
    name = "myapi"
    description = "Crawler for MyAPI datasets"
    config_class = MyCrawlConfig

    _http: HttpClient
    _validation_http: HttpClient | None

    async def setup(self, ctx: RunContext[MyCrawlConfig], stack: AsyncExitStack) -> None:
        self._http = await stack.enter_async_context(
            HttpClient.from_config(ctx.config)
        )
        self._validation_http = None if ctx.config.no_url_validation else self._http

    async def iterate_datasets(self, ctx: RunContext[MyCrawlConfig]) -> AsyncIterator[dict]:
        # Paginate your API here, yield raw items
        ...

    async def process(self, raw: dict, /) -> Result[OnedataDataset, Any] | None:
        # Parse raw → metadata record, then:
        return await OnedataDataset.build(
            pid=..., name=..., location=...,
            metadata=metadata_record,  # OpenAIRERecord or DataCiteRecord
            files=[OnedataFile(path=..., url=...) for ...],
            http=self._validation_http,
        )
```

**Key points:**

- `RawT` (first type param) is whatever `iterate_datasets` yields —
  `dict`, `str`, a custom dataclass, etc.
- `process()` runs inside N concurrent workers. It may do I/O
  (additional fetches, URL validation). Keep shared mutable state
  off `self` — `self._http` is safe (aiohttp sessions are
  concurrency-safe).
- Return `Ok(dataset)` → processed.jsonl, `Err(failure)` →
  rejected.jsonl, `None` → silent skip.

## Step 3: Lifecycle hooks (optional)

| Hook | When | Use case |
|------|------|----------|
| `setup(ctx, stack)` | Before crawl starts | Open HTTP clients, DB connections |
| `before_crawl(ctx)` | After setup, before workers | Validate preconditions (e.g. collection exists) |
| `after_crawl(ctx)` | After workers finish | Post-run reporting, cleanup |
| `run_context_name(config)` | Run dir creation | Customize suffix: `runs/…_myapi_<this>/` |

## Step 4: Extra commands (optional)

Use `@command` to add non-crawl commands (e.g. listing available
collections):

```python
from crawlers.core import command

@command
async def list_collections(self, config: MyApiConfig, stack: AsyncExitStack) -> None:
    """List available collections."""
    http = await stack.enter_async_context(HttpClient.from_config(config))
    result = await http.get_json("/collections")
    ...
```

The decorator infers the command name from the method
(`list_collections` → `list-collections`), the config class from
the type annotation, and the help text from the docstring. Override
any of these: `@command(name="ls", help="...")`.

## Step 5: Register the plugin

Add your plugin to `apps/crawlers/src/crawlers/plugins/__init__.py`:

```python
from crawlers.plugins.myapi.plugin import MyPlugin

REGISTERED_PLUGINS = [
    ...,
    MyPlugin(),
]
```

## Step 6: Verify

```bash
crawlers myapi crawl --help        # confirm args appear
crawlers myapi crawl my-coll -n 5  # small test run
```

Check `data/runs/<timestamp>_myapi_my-coll/` for:
- `config.json` — resolved configuration snapshot
- `state.json` — status, timestamps, stats
- `processed.jsonl` — successfully built datasets
- `rejected.jsonl` — failures with structured reasons

## Reference: imports cheat sheet

```python
# Framework essentials (single import)
from crawlers.core import (
    CrawlerPlugin, command,         # plugin base + command decorator
    CrawlConfig, HttpConfig, opt,   # config building blocks
    HttpClient,                     # async HTTP with retries
    Result, Ok, Err,                # explicit error handling
    RunContext,                     # crawl lifecycle context
)

# Data models
from crawlers.model import OnedataDataset, OnedataFile

# Metadata builders (pick one)
from crawlers.metadata.openaire import OpenAIRERecord
from crawlers.metadata.datacite import DataCiteRecord
```

## Reference plugins

| Plugin | Pattern | Notable features |
|--------|---------|-----------------|
| **Ecudo** | ID-based iteration → detail fetch in `process()` | `before_crawl()` validation, `list-orgs` command |
| **EODC** | Full items in listing → direct parse | STAC API, GeoJSON/datetime filters, `list-collections` |
| **Bgee** | HTML scraping → RDF/JSON-LD extraction | DataCite metadata, `after_crawl()` conformity check |
| **VIP** | Girder REST → recursive file resolution | Multi-level folder traversal in `process()` |
