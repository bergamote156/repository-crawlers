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
| `crawler.py` | Crawler orchestration |
| `metadata.py` | Custom metadata builder (optional) |
| `plugin.py` | Plugin class with CLI commands |

## Step 1: Create Plugin Directory

```bash
mkdir -p crawlers/plugins/myplugin
touch crawlers/plugins/myplugin/__init__.py
```

## Step 2: Define Configuration

Create `config.py` with your configuration classes:

```python
# crawlers/plugins/myplugin/config.py

__author__ = "Your Name"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from crawlers.core.config import ApiConfig, BaseCrawlConfig, ConfigBase, opt


class MyApiConfig(ApiConfig):
    """Base configuration for MyAPI connections."""
    
    base_url: str = opt(
        "https://api.example.com",
        description="API base URL",
    )


class MyCrawlConfig(MyApiConfig, BaseCrawlConfig, kw_only=True):
    """Full configuration for crawling."""
    
    # Required positional argument (cli= without dashes)
    collection: str = opt(
        ...,  # Required (no default)
        cli="collection",
        description="Collection ID to crawl",
    )
    
    # Optional with short alias
    max_records: int | None = opt(
        None,
        cli=("-n", "--max-records"),
        description="Maximum records to fetch",
    )
    
    # Optional settings
    page_size: int = opt(100, description="Items per API page")
    
    def __post_init__(self):
        """Validate configuration."""
        if not self.collection or self.collection.isspace():
            raise ValueError("Collection cannot be empty")
        self.collection = self.collection.strip()
```

**Key points:**
- Inherit from `BaseCrawlConfig` for standard options (output_dir, concurrency, etc.)
- Use `opt(...)` (ellipsis) for required fields
- Use `cli="name"` (no dashes) for positional arguments
- Add `__post_init__` for validation

## Step 3: Define Data Models

Create `models.py` with your dataset model:

```python
# crawlers/plugins/myplugin/models.py

__author__ = "Your Name"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

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
    
    # Optional fields
    keywords: list[str] = field(default_factory=list)
    issued: str | None = None
    
    # Store raw data for debugging
    _raw: dict = field(default_factory=dict, repr=False)
    
    def to_json(self) -> dict:
        """For JSONLWriter serialization."""
        return self._raw
```

**Key points:**
- Include `identifier`, `title`, `files` (required by converters)
- Add `to_json()` method for JSONL serialization
- Keep `_raw` for debugging

## Step 4: Implement Parser

Create `parser.py` to convert API responses to your model:

```python
# crawlers/plugins/myplugin/parser.py

__author__ = "Your Name"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from crawlers.core.processors.parsers import Parser
from crawlers.core.ui import console
from .models import MyDataset, MyFile


class MyParser(Parser[dict, MyDataset]):
    """Parses API responses into MyDataset."""
    
    def parse(self, raw: dict) -> MyDataset | None:
        """
        Parse raw API data.
        
        Returns:
            MyDataset or None if invalid/should be skipped
        """
        # Extract identifier
        identifier = raw.get("id")
        if not identifier:
            return None
        
        # Extract files
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
- Return `None` to skip invalid records
- Use `console.debug()` for skipped records

## Step 5: Implement API Client

Create `api.py` with your API client:

```python
# crawlers/plugins/myplugin/api.py

__author__ = "Your Name"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass
from typing import AsyncIterator

from crawlers.core.abc.api import ApiClient
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
        """
        Iterate over datasets from the API.
        
        Yields:
            Raw dataset dict from API
        """
        url = f"{self.base_url}/collections/{opts.collection}/items"
        yielded = 0
        page = 1
        
        while True:
            # Fetch page
            params = f"?page={page}&limit={opts.page_size}"
            data = await self.get_json(url + params)
            
            items = data.get("items", [])
            if not items:
                break
            
            for item in items:
                yield item
                yielded += 1
                
                if opts.max_items and yielded >= opts.max_items:
                    console.info(f"Reached max_items: {opts.max_items}")
                    return
            
            page += 1
            console.info(f"Page {page} | {yielded} items fetched")
        
        console.info(f"Iteration complete. Total: {yielded}")
    
    async def get_collections(self) -> list[dict]:
        """Fetch available collections (for list command)."""
        data = await self.get_json(f"{self.base_url}/collections")
        return data.get("collections", [])
```

**Two iteration patterns:**

| Pattern | Iterator yields | First processor | Use when |
|---------|-----------------|-----------------|----------|
| **Full records** | `dict` (record) | `ParserProcessor` | API returns full data in search |
| **IDs only** | `str` (ID) | `DatasetFetcher` | API requires separate detail request |

## Step 6: Implement Crawler

Create `crawler.py` to orchestrate the crawl:

```python
# crawlers/plugins/myplugin/crawler.py

__author__ = "Your Name"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from pathlib import Path
from typing import Any, AsyncIterable, cast

from crawlers.core.abc.api import ApiClient
from crawlers.core.crawler import BaseCrawler
from crawlers.core.metadata.openaire import OpenAIREBuilder
from crawlers.core.processors.converters import OnedataConverter
from crawlers.core.processors.parsers import ParserProcessor
from crawlers.core.processors.pipeline import ProcessorPipeline
from crawlers.core.processors.writers import JSONLWriter

from .api import MyClient, MyIteratorOpts
from .config import MyCrawlConfig
from .models import MyDataset
from .parser import MyParser


class MyCrawler(BaseCrawler[MyCrawlConfig]):
    """Crawler for MyDataSource."""
    
    def __init__(self, config: MyCrawlConfig):
        super().__init__(config)
        
        # Setup output paths
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        prefix = config.collection
        self._raw_output = output_dir / f"{prefix}_raw.jsonl"
        self._processed_output = output_dir / f"{prefix}_processed.jsonl"
    
    def create_client(self) -> MyClient:
        """Create API client."""
        return MyClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            max_retries=self.config.max_retries,
        )
    
    def create_iterator(self, client: ApiClient) -> AsyncIterable[Any]:
        """Create dataset iterator."""
        my_client = cast(MyClient, client)
        
        opts = MyIteratorOpts(
            collection=self.config.collection,
            page_size=self.config.page_size,
            max_items=self.config.max_records,
        )
        
        return my_client.iterate_datasets(opts)
    
    def build_pipeline(self, client: ApiClient) -> ProcessorPipeline:
        """Build processing pipeline."""
        return ProcessorPipeline([
            # 1. Parse: dict -> MyDataset
            ParserProcessor(parser=MyParser()),
            
            # 2. Write raw data
            JSONLWriter(output_path=self._raw_output),
            
            # 3. Convert: MyDataset -> OnedataDataset
            OnedataConverter(
                metadata_builder=OpenAIREBuilder(),  # or custom builder
            ),
            
            # 4. Write processed data
            JSONLWriter(output_path=self._processed_output),
        ])
    
    def get_max_items(self) -> int | None:
        """For progress bar."""
        return self.config.max_records
    
    def _get_banner_subtitle(self) -> str | None:
        """Banner subtitle."""
        return f"Collection: {self.config.collection}"
```

**Optional: Add validation hook:**

```python
async def before_crawl(self, client: ApiClient) -> None:
    """Validate collection exists."""
    my_client = cast(MyClient, client)
    
    collections = await my_client.get_collections()
    if not any(c["id"] == self.config.collection for c in collections):
        console.error(f"Collection '{self.config.collection}' not found")
        sys.exit(1)
```

## Step 7: Create Plugin Class

Create `plugin.py` with CLI commands:

```python
# crawlers/plugins/myplugin/plugin.py

__author__ = "Your Name"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from rich.table import Table

from crawlers.core.plugin import CrawlerPlugin, command
from crawlers.core.ui import console
from .config import MyApiConfig, MyCrawlConfig


class MyPlugin(CrawlerPlugin):
    """Plugin for MyDataSource."""
    
    name = "myplugin"
    description = "Crawler for MyDataSource datasets"
    
    @command("crawl", MyCrawlConfig, help="Crawl datasets from collection")
    async def run_crawl(self, config: MyCrawlConfig) -> None:
        """Execute crawling."""
        # Lazy import for faster CLI startup
        from .crawler import MyCrawler
        
        crawler = MyCrawler(config)
        await crawler.run()
    
    @command("list-collections", MyApiConfig, help="List available collections")
    async def list_collections(self, config: MyApiConfig) -> None:
        """List collections."""
        from .api import MyClient
        
        async with MyClient(
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
        ) as client:
            with console.status("Fetching collections..."):
                collections = await client.get_collections()
            
            table = Table(title=f"Collections ({len(collections)})")
            table.add_column("ID", style="cyan")
            table.add_column("Title")
            
            for coll in collections:
                table.add_row(coll.get("id"), coll.get("title", "-"))
            
            console.print(table)
```

**Key points:**
- Use lazy imports in command methods for faster CLI startup
- Define `name` and `description` for CLI help
- Each command gets its own config class

## Step 8: Register Plugin

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

## Step 9: Test Your Plugin

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

# Check output
head data/my-collection_processed.jsonl
```

## Directory Structure

Your final plugin structure:

```
crawlers/plugins/myplugin/
├── __init__.py          # Empty or re-exports
├── api.py               # MyClient
├── config.py            # MyApiConfig, MyCrawlConfig
├── crawler.py           # MyCrawler
├── models.py            # MyDataset, MyFile
├── parser.py            # MyParser
└── plugin.py            # MyPlugin
```

## Optional Enhancements

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

Use in crawler:

```python
OnedataConverter(metadata_builder=MyDataCiteBuilder())
```

### Additional Processors

Add URL validation, filtering, etc.:

```python
from crawlers.core.processors.validators import URLValidator
from crawlers.core.processors.filters import DiversityFilter

def build_pipeline(self, client: ApiClient) -> ProcessorPipeline:
    my_client = cast(MyClient, client)
    
    return ProcessorPipeline([
        ParserProcessor(parser=MyParser()),
        
        URLValidator(
            validate_fn=my_client.validate_url,
            enabled=self.config.validate_urls,
        ),
        
        DiversityFilter(
            max_similar=10,
            enabled=self.config.filter_duplicates,
        ),
        
        JSONLWriter(output_path=self._raw_output),
        OnedataConverter(metadata_builder=MyMetadataBuilder()),
        JSONLWriter(output_path=self._processed_output),
    ])
```

### Nested Configuration

For complex processor config:

```python
# config.py
class URLValidatorConfig(ConfigBase):
    enabled: bool = opt(True)
    invalid_url_log: str | None = opt("invalid.jsonl")

class ProcessorsConfig(ConfigBase):
    url_validator: URLValidatorConfig = opt(default_factory=URLValidatorConfig)

class MyCrawlConfig(BaseCrawlConfig, kw_only=True):
    ...
    processors: ProcessorsConfig = opt(default_factory=ProcessorsConfig)
```

YAML configuration:

```yaml
plugins:
  myplugin:
    processors:
      url_validator:
        enabled: true
        invalid_url_log: "invalid.jsonl"
```

## Reference Implementations

Study existing plugins for patterns:

| Plugin | Pattern | Features |
|--------|---------|----------|
| `ecudo` | ID-based iteration | `DatasetFetcher`, `DiversityFilter`, `URLValidator` |
| `eodc` | Full record iteration | `ParserProcessor`, custom `DataCiteBuilder` |

## Further Reading

- [Configuration System](arch/configuration.md) - `opt()`, sources, priority
- [Processing Pipeline](arch/processors.md) - Custom processors
- [Metadata Generation](arch/metadata.md) - Custom builders
- [Crawling System](arch/crawling.md) - `ApiClient`, `BaseCrawler`
- [Framework Architecture](arch/ARCHITECTURE.md) - Complete overview
