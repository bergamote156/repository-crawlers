---
title: Writing Plugins
topic: crawlers/guides/writing-plugins
generated: 2026-04-01
last_reviewed: 2026-04-01
source_modules:
  - crawlers/default/plugin.py
  - crawlers/default/config.py
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
  public-data-crawlers: d8a4e8e
status: draft
---

# Writing Plugins

This guide walks you through creating a new crawler plugin. You will
implement an API client, a parser, a configuration, and a plugin
class — then register it so the CLI can discover it.

> For the architecture behind the plugin system, see
> [Plugin System](../arch/plugin-system.md). For the pipeline
> mechanics, see [Processing](../arch/processing.md).

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

Define a dataclass for your parsed dataset. It must satisfy the
protocol expected by your chosen metadata builder — for OpenAIRE,
this means `identifier`, `title`, `description`, `publisher`,
`issued`, `files`, `language`, `keywords`, `access_level`,
`spatial`, `temporal`. For DataCite, you need `identifier`, `title`,
`datetime`, `geometry`, `files`, `self_link`.

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

Subclass `ApiClient` with your API's iterator options type and the
type yielded by the iterator:

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
  `str` and use `DatasetFetcher` in the pipeline (like Ecudo).

## Step 3: Configuration

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

The minimal plugin subclasses `DefaultCrawlerPlugin` and implements
`prepare_crawl()`:

```python
class MyPlugin(DefaultCrawlerPlugin):
    name = "myapi"
    description = "Crawler for My API"
    config_class = MyCrawlConfig

    def prepare_crawl(self, config: DefaultCrawlConfig) -> DefaultCrawlSpec:
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

```python
from crawlers.plugins.myapi.plugin import MyPlugin

REGISTERED_PLUGINS = [
    EcudoPlugin(),
    EODCPlugin(),
    MyPlugin(),       # <-- add here
]
```

Your plugin is now available as `crawlers myapi crawl ...`.

## Custom Pipeline

Override `build_pipeline()` when you need extra processing stages
or a different processor order. Ecudo does this to add a
`DatasetFetcher` (because the API returns IDs, not full items) and
a `DiversityFilter`:

```python
def build_pipeline(
    self, config: DefaultCrawlConfig, spec: DefaultCrawlSpec, ctx: DefaultRunContext
) -> ProcessorPipeline:
    return ProcessorPipeline(
        processors=[
            DatasetFetcher(
                fetch_fn=cast(MyClient, spec.client).get_item,
                parser=spec.parser,
            ),
            URLValidator(
                validate_fn=spec.client.validate_url,
                enabled=not config.no_url_validation,
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
ParserProcessor → URLValidator → Tap(raw) → OnedataConverter → Tap(processed)
```

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

Override `before_crawl()` to validate preconditions after the client
session is open. Ecudo uses this to verify the requested
organization exists:

```python
async def before_crawl(self, spec: DefaultCrawlSpec) -> None:
    client = cast(MyClient, spec.client)
    result = await client.validate_collection(self._collection)
    if isinstance(result, Err):
        console.error(f"Collection not found: {self._collection}")
        sys.exit(1)
```

Override `after_crawl()` for post-crawl actions (cleanup, summary
reporting, etc.).

## Real Examples

The two built-in plugins demonstrate different patterns:

**EODC** (`crawlers/plugins/eodc/`) — the simpler case:
- STAC API returns full items → uses default pipeline with
  `ParserProcessor`.
- No `build_pipeline()` override needed.
- Custom `DataCiteBuilder` subclass for Sentinel-1 metadata
  defaults.
- `list-collections` extra command.

**Ecudo** (`crawlers/plugins/ecudo/`) — the advanced case:
- API returns IDs → overrides `build_pipeline()` with
  `DatasetFetcher`.
- Adds `DiversityFilter` for title deduplication.
- Nested `DiversityFilterConfig` for YAML-only tuning.
- `before_crawl()` validates organization exists.
- `list-orgs` extra command.

## Related Documentation

- **[Plugin System](../arch/plugin-system.md)** — architecture and
  lifecycle details
- **[Configuration](../arch/configuration.md)** — config system
  deep-dive
- **[Processing](../arch/processing.md)** — pipeline and processors
- **[Metadata](../arch/metadata.md)** — metadata builder
  extensibility
- **[Glossary](../arch/glossary.md)** — quick definitions
