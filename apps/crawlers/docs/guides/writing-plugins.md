---
audience: integrator
source_modules:
  - apps/crawlers/src/crawlers/core/__init__.py
  - apps/crawlers/src/crawlers/core/config.py
  - apps/crawlers/src/crawlers/core/dataset.py
  - apps/crawlers/src/crawlers/core/http.py
  - apps/crawlers/src/crawlers/core/plugin.py
  - apps/crawlers/src/crawlers/plugins/__init__.py
  - apps/crawlers/src/crawlers/plugins/ecudo/plugin.py
source_commits:
  public-data-crawlers: 7ce5a5e
---

# Writing Plugins

By the end of this guide you'll have a working crawler runnable as
`crawlers myapi crawl <collection>`.

> [!TIP]
> Study the production plugin closest to your use case 
> (see [Reference plugins](#reference-plugins) at the bottom).
> Ecudo is a good default starting point.

## What you need to implement

A plugin extends `CrawlerPlugin[RawT, ConfigT]` and provides:

1. **Config class** — declares your CLI arguments, YAML keys, and
   defaults by extending `CrawlConfig`.
2. **`iterate_datasets(ctx)`** — async generator yielding raw items
   from the upstream API.
3. **`process(raw)`** — turns each raw item into a
   `Result[OnedataDataset, failure]` (or `None` to skip).

The framework handles everything else: parallel worker pool, JSONL
persistence, progress display, run directories, dataset validation,
and state management.

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

> [!TIP]
> **Source:** `apps/crawlers/src/crawlers/plugins/ecudo/plugin.py#EcudoCrawlConfig`
> for a real-world example of this pattern.

Plugin declares its config as a pair of dataclasses: an
**API config** (for non-crawl commands if any) and a **crawl config**
(for the full crawl). Both compose framework-provided base classes
via multiple inheritance:

```python
from typing import Annotated

from crawlers.core import CliPositional, CrawlConfig, HttpConfig, opt


class MyApiConfig(HttpConfig):
    """Base HTTP config — also used by non-crawl commands."""

    base_url: str = opt("https://api.example.com/v1", description="API base URL")


class MyCrawlConfig(MyApiConfig, CrawlConfig, kw_only=True):
    """Full crawl config."""

    collection: Annotated[str, CliPositional] = opt(
        description="Collection to crawl",
    )
    page_size: int = opt(100, description="Items per API page")
```

This declaration is all the framework needs to generate CLI
arguments, parse YAML files, read environment variables, and
produce `--help` output — with zero boilerplate on your part.

### Config inheritance

The base classes compose via diamond inheritance:

- **`HttpConfig`** provides `base_url`, `timeout`, `max_retries`.
- **`OutputConfig`** provides `output_dir`.
- **`ProcessingConfig`** provides `concurrency`, `queue_size`.
- **`CrawlConfig`** extends all three and adds `max_records`,
  `no_url_validation`.

Your `MyApiConfig` subclasses `HttpConfig` with a custom
`base_url` default. Your `MyCrawlConfig` extends both `MyApiConfig`
and `CrawlConfig`. Python's MRO merges the shared `HttpConfig`
ancestor correctly — each field is initialized exactly once. Always
pass `kw_only=True` on the leaf class to avoid ordering conflicts
between required and defaulted fields.

Each class in the MRO becomes a separate argument group in
`--help`, so output is organized by concern:

```
$ crawlers myapi crawl --help
MyCrawlConfig:
  collection          Collection to crawl
  --page-size …       Items per API page

MyApiConfig:
  --base-url …        API base URL

HttpConfig:
  --timeout …         Request timeout in seconds
  --max-retries …     Maximum retry attempts

CrawlConfig:
  -n, --max-records … Maximum number of items to fetch
  --no-url-validation  Disable HEAD-probe URL validation

OutputConfig:
  -o, --output-dir …  Output directory for crawled data

ProcessingConfig:
  --concurrency …     Number of concurrent workers
  --queue-size …      Size of the processing queue
```

### opt() — field declaration

> [!TIP]
> **Source:** `packages/confline/src/confline/config/schema.py#opt`

`opt()` replaces `dataclasses.field()`. It carries
**source-agnostic** metadata — defaults, description, validation.
Source-specific naming (CLI flags, ENV var names, YAML paths) lives
in `Annotated[...]` annotations instead.

Common parameters:

| Parameter | Default              | Effect |
|-----------|----------------------|--------|
| `default` | `MISSING` (required) | Default value. |
| `description` | `""`                 | Help text for CLI `--help`. |
| `choices` | `None`               | Restrict to allowed values. |
| `secret` | `False`              | Mask value in `--show-config` output. |
| `excluded_from` | `()`                 | Source classes to skip — e.g. `[CliSource]`. |

Without any annotations, a field named `page_size` auto-generates:
- CLI flag `--page-size`
- ENV var `CRAWLER_PAGE_SIZE`
- YAML key `page_size`

### Source annotations

When the auto-derived name doesn't fit, override it with an
`Annotated[T, marker]` type annotation. Each marker is imported
from `crawlers.core`:

| Marker | Effect | Example |
|--------|--------|---------|
| `CliAlias(*names)` | Override CLI flag names | `Annotated[int, CliAlias("-n", "--max-records")]` |
| `CliPositional` | Positional CLI argument | `Annotated[str, CliPositional]` |
| `EnvAlias(name)` | Override ENV variable name | `Annotated[str, EnvAlias("LEGACY_KEY")]` |
| `YamlPath(*parts)` | Override YAML lookup path | `Annotated[str, YamlPath("legacy", "host")]` |

To exclude a field from a source entirely, use
`excluded_from=[CliSource]` (or `EnvSource`, `YamlSource`) in
`opt()`.

### Resolution priority

When the same field is set in multiple sources, the framework
resolves it in a fixed order — first match wins:

1. **CLI argument** (highest priority)
2. **YAML — command scope** (`plugins.<name>.commands.<cmd>.<key>`)
3. **YAML — plugin scope** (`plugins.<name>.<key>`)
4. **YAML — global scope** (`global.<key>`)
5. **Environment variable** (`CRAWLER_<UPPER_FIELD_NAME>`)
6. **opt() default** (lowest priority)

### YAML config file layout

A YAML file passed via `-c config.yaml` supports three scopes.
More specific scopes win over less specific ones:

```yaml
global:
  timeout: 30
  output_dir: ./output

plugins:
  ecudo:
    base_url: http://custom.ecudo.pl
    timeout: 60

    commands:
      crawl:
        page_size: 50
        max_records: 1000
```

For `timeout` when running `crawlers ecudo crawl`: the plugin
scope sets it to **60**, which wins over the global scope's 30.
The command scope for `page_size` sets it to **50** — lower
scopes aren't checked.


## Step 2: Plugin class

> [!TIP]
> **Source:** `apps/crawlers/src/crawlers/plugins/ecudo/plugin.py#EcudoPlugin`

```python
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from typing import Any

from crawlers.core import (
    CrawlerPlugin, HttpClient, Ok, Result, RunContext,
)
from crawlers.core.dataset import OnedataDataset, OnedataFile


class MyPlugin(CrawlerPlugin[dict, MyCrawlConfig]):
    """Crawler for MyAPI datasets."""

    name = "myapi"
    description = "Crawler for MyAPI datasets"
    config_class = MyCrawlConfig

    _http: HttpClient

    async def setup(self, ctx: RunContext[MyCrawlConfig], stack: AsyncExitStack) -> None:
        self._http = await stack.enter_async_context(
            HttpClient.from_config(ctx.config)
        )

    async def iterate_datasets(
        self, ctx: RunContext[MyCrawlConfig],
    ) -> AsyncIterator[dict]:
        # Paginate your API here, yield raw items.
        ...

    async def process(self, raw: dict, /) -> Result[OnedataDataset, Any] | None:
        dataset = OnedataDataset(
            name=...,
            target_dir=...,
            pid=...,
            metadata_xml=metadata_record.to_xml(),
            files=tuple(OnedataFile(path=..., url=...) for ...),
        )
        return Ok(dataset)
```

Three class attributes — `name`, `description`, `config_class` —
and two abstract methods — `iterate_datasets`, `process` — are the
minimum contract.

**What the framework handles for you:**

- **`crawl` command** — auto-registered when `name` is set. No
  `@command` decorator needed.
- **Parallel execution** — `iterate_datasets` feeds a bounded
  `asyncio.Queue`; N workers call `process` concurrently.
- **Dataset validation** — every `Ok(dataset)` passes through the
  framework's `DatasetValidator` (non-empty files, unique paths,
  URL reachability) before being persisted. You just return the
  dataset.
- **Output** — `processed.jsonl` and `rejected.jsonl` sinks,
  state tracking, Rich progress bar, summary display.

**Key points:**

- **`RawT`** (first type param) is whatever `iterate_datasets`
  yields — `dict`, `str`, a custom dataclass.
- **`process()`** runs inside concurrent workers. It may do I/O
  (additional API fetches via `self._http`). Keep shared mutable
  state off `self` — `HttpClient` is concurrency-safe.
- Return `Ok(dataset)` for success, `Err(failure)` for rejection,
  `None` for silent skip.


## Step 3: Lifecycle hooks (optional)

| Hook | When | Use case |
|------|------|----------|
| `setup(ctx, stack)` | Before crawl starts | Open HTTP clients, API facades |
| `before_crawl(ctx)` | After setup, before workers | Validate preconditions (e.g. collection exists) |
| `after_crawl(ctx)` | After workers finish | Post-run reporting, cleanup |
| `run_context_name(config)` | Run dir creation | Customize suffix: `runs/…_myapi_<this>/` |

> [!TIP]
> **Source:** Ecudo uses all four hooks —
> `apps/crawlers/src/crawlers/plugins/ecudo/plugin.py#EcudoPlugin.before_crawl`.

Resources opened in `setup` should be registered on the
`AsyncExitStack` so they close automatically regardless of whether
the crawl completes, fails, or is interrupted.


## Step 4: Extra commands (optional)

Use `@command` to add non-crawl commands (e.g. listing available
collections):

```python
from crawlers.core import command

@command(name="list-orgs")
async def list_organizations(
    self, config: MyApiConfig, stack: AsyncExitStack,
) -> None:
    """List all available organizations."""
    http = await stack.enter_async_context(HttpClient.from_config(config))
    result = await http.get_json("/organizations")
    ...
```

The decorator infers the config class from the type annotation and
the help text from the docstring. The command name defaults to the
method name with underscores replaced by dashes; override with
`@command(name="ls")`.

> [!TIP]
> **Source:** `apps/crawlers/src/crawlers/plugins/ecudo/plugin.py#EcudoPlugin.list_organizations`


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
# Framework essentials
from crawlers.core import (
    CrawlerPlugin, command,            # plugin base + command decorator
    CrawlConfig, HttpConfig, opt,      # config building blocks
    CliAlias, CliPositional,           # source-specific annotations
    EnvAlias, YamlPath,                # env/yaml overrides
    CliSource, EnvSource, YamlSource,  # for excluded_from=
    HttpClient,                        # async HTTP with retries
    Result, Ok, Err,                   # explicit error handling
    RunContext,                        # crawl lifecycle context
)

# Data models
from crawlers.core.dataset import OnedataDataset, OnedataFile

# Metadata builders (pick one or both)
from crawlers.metadata.openaire import OpenAIRERecord
from crawlers.metadata.datacite import DataCiteRecord
```


## Reference plugins

| Plugin | Pattern | Notable features |
|--------|---------|-----------------|
| **Ecudo** | ID-based iteration, detail fetch in `process()` | `before_crawl()` validation, `list-orgs` command |
| **EODC** | Full items in listing, direct parse | STAC API, GeoJSON/datetime filters, `list-collections` |
| **Bgee** | HTML scraping, RDF/JSON-LD extraction | DataCite metadata, `after_crawl()` conformity check |
| **VIP** | Girder REST, recursive file resolution | Multi-level folder traversal in `process()` |
| **Topanat** | TopAnat job results, file listing | Dynamic query URLs |
