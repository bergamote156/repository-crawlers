# Plugin Development Guide

This guide walks you through creating a new crawler plugin from scratch.

## Overview

A plugin consists of these components:

| File | Purpose |
|------|---------|
| `config.py` | Configuration classes with CLI/YAML/ENV options |
| `api.py` | API client for the data source |
| `models.py` | Data models for parsed datasets |
| `parser.py` | Parser converting raw API data to models |
| `plugin.py` | Plugin class with crawl logic and CLI commands |
| `metadata.py` | Custom metadata builder (optional) |

## Step 1: Create Plugin Directory

```bash
mkdir -p crawlers/plugins/myplugin
touch crawlers/plugins/myplugin/__init__.py
```

## Step 2: Define Configuration

Create `config.py` with your configuration classes:

```python
# crawlers/plugins/myplugin/config.py

from crawlers.core.abc.config import ConfigBase, opt
from crawlers.core.default.config import ApiConfig, DefaultCrawlConfig


class MyApiConfig(ApiConfig):
    """Base configuration for MyAPI connections."""

    base_url: str = opt(
        "https://api.example.com",
        description="API base URL",
    )


class MyCrawlConfig(MyApiConfig, DefaultCrawlConfig, kw_only=True):
    """Full configuration for crawling."""

    # Required positional argument (cli= without dashes)
    collection: str = opt(
        ...,  # Required (no default)
        cli="collection",
        description="Collection ID to crawl",
    )

    def __post_init__(self):
        """Validate configuration."""
        if not self.collection or self.collection.isspace():
            raise ValueError("Collection cannot be empty")
        self.collection = self.collection.strip()

    def get_url_validator_enabled(self) -> bool:
        return not self.no_url_validation
```

**Key points:**
- Inherit from `DefaultCrawlConfig` for standard options (output_dir, concurrency, max_records, etc.)
- Use `opt(...)` (Ellipsis) for required fields
- Use `cli="name"` (no dashes) for positional arguments
- Add `__post_init__` for validation

## Step 3: Define Data Models

Create `models.py` with your dataset model:

```python
# crawlers/plugins/myplugin/models.py

from dataclasses import dataclass, field
from typing import Sequence


@dataclass
class MyFile:
    """File from dataset."""
    name: str
    url: str


@dataclass
class MyDataset:
    """Parsed dataset model."""
    identifier: str
    title: str
    description: str
    files: Sequence[MyFile]

    keywords: list[str] = field(default_factory=list)
    issued: str | None = None

    # Store raw data for debugging
    _raw: dict = field(default_factory=dict, repr=False)

    def to_json(self) -> dict:
        """For Tap serialization."""
        return self._raw
```

**Key points:**
- Include `identifier`, `title`, `files` (required by converters/validators)
- Add `to_json()` method for JSONL serialization
- Keep `_raw` for debugging

## Step 4: Implement Parser

Create `parser.py` to convert API responses to your model:

```python
# crawlers/plugins/myplugin/parser.py

from crawlers.core.processors.parsers import Parser
from crawlers.core.ui import console
from .models import MyDataset, MyFile


class MyParser(Parser[dict, MyDataset]):
    """Parses API responses into MyDataset."""

    def parse(self, raw: dict) -> MyDataset | None:
        """
        Parse raw API data.

        Returns:
            MyDataset or None if invalid/should be skipped silently
        """
        identifier = raw.get("id")
        if not identifier:
            return None

        files = self._parse_files(raw.get("assets", {}))
        if not files:
            console.debug(f"Skipping {identifier}: no files")
            return None

        return MyDataset(
            identifier=identifier,
            title=raw.get("title", "Untitled"),
            description=raw.get("description", ""),
            files=files,
            keywords=raw.get("keywords", []),
            issued=raw.get("datetime"),
            _raw=raw,
        )

    def _parse_files(self, assets: dict) -> list[MyFile]:
        """Extract files from assets."""
        files = []
        for name, asset in assets.items():
            url = asset.get("href")
            if url:
                files.append(MyFile(name=name, url=url))
        return files
```

**Key points:**
- Implement `Parser[InputType, OutputType]` protocol
- Return `None` to silently skip records (not logged to rejection sink)
- Use `console.debug()` for informational skip messages

## Step 5: Implement API Client

Create `api.py` with your API client:

```python
# crawlers/plugins/myplugin/api.py

from dataclasses import dataclass
from typing import AsyncIterator

from crawlers.core.abc.api import ApiClient
from crawlers.core.result import Ok, Result
from crawlers.core.ui import console


@dataclass
class MyIteratorOpts:
    """Options for iteration."""
    collection: str
    page_size: int = 100
    max_items: int | None = None


class MyClient(ApiClient[MyIteratorOpts, dict]):
    """API client for MyDataSource."""

    async def iterate_datasets(self, opts: MyIteratorOpts) -> AsyncIterator[dict]:
        """Paginate the API and yield full records (dict)."""
        page = 1
        yielded = 0
        while True:
            url = f"{self.base_url}/collections/{opts.collection}/items"
            params = f"?page={page}&limit={opts.page_size}"
            result = await self.get_json(url + params)

            match result:
                case Ok(data):
                    items = data.get("items", [])
                    if not items:
                        break
                    console.info(f"Page {page} | {yielded} fetched")
                    for item in items:
                        yield item
                        yielded += 1
                        if opts.max_items and yielded >= opts.max_items:
                            console.info(f"Reached max_items limit: {opts.max_items}")
                            return
                    page += 1
                case _:
                    break

    async def get_collections(self) -> Result[list[dict], object]:
        """Fetch available collections."""
        result = await self.get_json(f"{self.base_url}/collections")
        return result.map(lambda d: d.get("collections", []))
```

**Two iteration patterns:**

| Pattern | Iterator yields | First processor | Use when |
|---------|-----------------|-----------------|----------|
| **Full records** | `dict` (record) | `ParserProcessor` | API returns full data in search |
| **IDs only** | `str` (ID) | `DatasetFetcher` | API requires separate detail request |

## Step 6: Create Plugin Class

Create `plugin.py` with the plugin definition:

```python
# crawlers/plugins/myplugin/plugin.py

from typing import cast

from rich.table import Table

from crawlers.core.abc.plugin import command
from crawlers.core.default.config import DefaultCrawlConfig
from crawlers.core.default.plugin import CrawlSpec, DefaultCrawlerPlugin
from crawlers.core.metadata.openaire import OpenAIREBuilder
from crawlers.core.result import Ok
from crawlers.core.ui import console
from .api import MyClient, MyIteratorOpts
from .config import MyApiConfig, MyCrawlConfig
from .parser import MyParser


class MyPlugin(DefaultCrawlerPlugin):
    """Plugin for MyDataSource."""

    name = "myplugin"
    description = "Crawler for MyDataSource datasets"
    config_class = MyCrawlConfig  # type: ignore[assignment]

    def prepare_crawl(self, config: DefaultCrawlConfig) -> CrawlSpec:
        cfg = cast(MyCrawlConfig, config)
        return CrawlSpec(
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
            metadata_builder=OpenAIREBuilder(),  # or custom builder
            run_context_name=cfg.collection,
            banner_subtitle=f"Collection: {cfg.collection}",
            max_items=cfg.max_records,
            url_validation=cfg.get_url_validator_enabled(),
        )

    @command("list-collections", MyApiConfig, help="List available collections")
    async def list_collections(self, config: MyApiConfig) -> None:
        """List collections."""
        async with MyClient(
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
        ) as client:
            with console.status("Fetching collections..."):
                result = await client.get_collections()

        if result.is_err():
            console.error(f"Failed: {result.err()}")
            return

        collections = result.unwrap()
        table = Table(title=f"Collections ({len(collections)})")
        table.add_column("ID", style="cyan")
        table.add_column("Title")
        for coll in collections:
            table.add_row(coll.get("id"), coll.get("title", "-"))
        console.print(table)
```

**Key points:**
- Inherit from `DefaultCrawlerPlugin` (not `CrawlerPlugin` directly)
- Set `config_class` to your crawl config class
- `prepare_crawl()` returns a `CrawlSpec` — the framework drives execution
- The `crawl` command is auto-registered; add extra commands with `@command`
- Use lazy imports inside `@command` methods for faster CLI startup

## Step 7: Register Plugin

Add to `crawlers/plugins/__init__.py`:

```python
from crawlers.plugins.ecudo.plugin import EcudoPlugin
from crawlers.plugins.eodc.plugin import EODCPlugin
from crawlers.plugins.myplugin.plugin import MyPlugin  # Add import

REGISTERED_PLUGINS = [
    EcudoPlugin(),
    EODCPlugin(),
    MyPlugin(),  # Add instance
]
```

## Step 8: Test Your Plugin

```bash
# Check plugin is registered
python -m crawlers --list-plugins

# Show help
python -m crawlers myplugin --help
python -m crawlers myplugin crawl --help

# List collections
python -m crawlers myplugin list-collections

# Run crawl
python -m crawlers myplugin crawl my-collection -n 10

# Check output (in run directory)
ls data/runs/
cat data/runs/<timestamp>_myplugin_my-collection/state.json
```

## Directory Structure

Final plugin structure:

```
crawlers/plugins/myplugin/
├── __init__.py          # Empty or re-exports
├── api.py               # MyClient, MyIteratorOpts
├── config.py            # MyApiConfig, MyCrawlConfig
├── models.py            # MyDataset, MyFile
├── parser.py            # MyParser
└── plugin.py            # MyPlugin
```

## Optional Enhancements

### Validation Hook

Override `before_crawl()` for pre-flight validation:

```python
async def before_crawl(self, spec: CrawlSpec) -> None:
    client = cast(MyClient, spec.client)
    cfg = cast(MyCrawlConfig, self._config)

    with console.status("Validating collection..."):
        result = await client.get_collections()

    match result:
        case Ok(collections):
            if not any(c["id"] == cfg.collection for c in collections):
                console.error(f"Collection '{cfg.collection}' not found")
                sys.exit(1)
        case Err(err):
            console.error(f"Validation failed: {err}")
            sys.exit(1)
```

### Custom Metadata Builder

For source-specific metadata, create `metadata.py`:

```python
from crawlers.core.metadata.datacite import DataCiteBuilder

class MyDataCiteBuilder(DataCiteBuilder):
    """Custom DataCite builder."""
    creator_name = "My Organization"
    publisher_name = "My Publisher"
    default_subjects = ["Science", "Data"]
```

Use in `prepare_crawl`:

```python
metadata_builder=MyDataCiteBuilder()
```

### Custom Pipeline

Override `build_pipeline()` to use `DatasetFetcher`, add `DiversityFilter`, etc.:

```python
def build_pipeline(self, spec: CrawlSpec, ctx: DefaultRunContext) -> ProcessorPipeline:
    client = cast(MyClient, spec.client)
    cfg = cast(MyCrawlConfig, self._crawl_config)

    return ProcessorPipeline(
        processors=[
            DatasetFetcher(
                fetch_fn=client.get_dataset_details,
                parser=spec.parser,
            ),
            URLValidator(
                validate_fn=client.validate_url,
                enabled=spec.url_validation,
            ),
            DiversityFilter(
                max_similar=10,
                enabled=True,
            ),
            Tap(ctx.raw_sink, transform=lambda d: d.to_json()),
            OnedataConverter(metadata_builder=spec.metadata_builder),
            Tap(ctx.processed_sink, transform=lambda d: d.to_json()),
        ],
        rejection_sink=ctx.rejection_sink,
    )
```

### Nested Processor Configuration

For configurable processor settings:

```python
# config.py
class URLValidatorConfig(ConfigBase):
    enabled: bool = opt(True)

class DiversityFilterConfig(ConfigBase):
    enabled: bool = opt(True)
    max_similar: int = opt(10)

class ProcessorsConfig(ConfigBase):
    url_validator: URLValidatorConfig = opt(default_factory=URLValidatorConfig)
    diversity_filter: DiversityFilterConfig = opt(default_factory=DiversityFilterConfig)

class MyCrawlConfig(DefaultCrawlConfig, kw_only=True):
    processors: ProcessorsConfig = opt(default_factory=ProcessorsConfig)

    def get_diversity_filter_enabled(self) -> bool:
        return self.processors.diversity_filter.enabled
```

YAML configuration:

```yaml
plugins:
  myplugin:
    processors:
      url_validator:
        enabled: true
      diversity_filter:
        enabled: true
        max_similar: 5
```

## Reference Implementations

Study existing plugins for patterns:

| Plugin | Iteration | Pipeline extras |
|--------|-----------|-----------------|
| `ecudo` | ID-based (`DatasetFetcher`) | `DiversityFilter`, `URLValidator` |
| `eodc` | Full records (`ParserProcessor`) | Custom `DataCiteBuilder` |

## Further Reading

- [Configuration System](arch/configuration.md) - `opt()`, sources, priority
- [Processing Pipeline](arch/processors.md) - Custom processors, Tap, Sinks
- [Metadata Generation](arch/metadata.md) - Custom builders
- [Crawling System](arch/crawling.md) - `ApiClient`, `CrawlSpec`, `RunContext`
- [Framework Architecture](arch/ARCHITECTURE.md) - Complete overview
