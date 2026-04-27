---
title: Plugin System
description: >
  How crawler plugins are structured, discovered, and executed.
  Covers the CrawlerPlugin base class, command registration, config
  dispatch, HttpClient, crawl lifecycle, and plugin registry.
topic: crawlers/arch/plugin-system
audience: internal-developer-onboarding
generated: 2026-04-01
last_reviewed: 2026-04-10
source_modules:
  - apps/crawlers/src/crawlers/core/plugin.py
  - apps/crawlers/src/crawlers/core/http.py
  - apps/crawlers/src/crawlers/core/runner.py
  - apps/crawlers/src/crawlers/core/workspace.py
  - apps/crawlers/src/crawlers/core/crawl_config.py
  - apps/crawlers/src/crawlers/model/dataset.py
  - apps/crawlers/src/crawlers/cli.py
  - apps/crawlers/src/crawlers/plugins/__init__.py
source_commits:
  repository-crawlers: cff14ee
status: draft
---

# Plugin System

<sub>📄 `apps/crawlers/src/crawlers/core/plugin.py:128-269`</sub>

A plugin is a self-contained crawler for one external data source.
[**CrawlerPlugin**](#crawlerplugin) is the single base class that
all plugins extend — it handles command registration, argparse
generation, multi-source config loading, the crawl lifecycle, and
parallel execution. You provide the source-specific logic:
[`iterate_datasets()`](#iteration-and-processing) to list items
from the upstream API, and
[`process()`](#iteration-and-processing) to turn each item into an
[OnedataDataset](#onedatadataset-assembly).

```mermaid
classDiagram
    class CrawlerPlugin~RawT, ConfigT~ {
        +name : str
        +description : str
        +config_class : type
        +setup(ctx, stack)
        +before_crawl(ctx)
        +iterate_datasets(ctx) AsyncIterator~RawT~
        +process(raw: RawT) Result | None
        +after_crawl(ctx)
        +run_context_name(config) str
    }

    class CommandDef {
        +name : str
        +help : str
        +method_name : str
        +config_class
    }

    class EcudoPlugin
    class EODCPlugin
    class BgeePlugin
    class VipPlugin

    CrawlerPlugin <|-- EcudoPlugin
    CrawlerPlugin <|-- EODCPlugin
    CrawlerPlugin <|-- BgeePlugin
    CrawlerPlugin <|-- VipPlugin

    CrawlerPlugin "1" o-- "many" CommandDef : _commands

    style CrawlerPlugin fill:#E6E6FA,stroke:#5B4B8A,color:#000
    style CommandDef fill:#A8DADC,stroke:#1864AB,color:#000
    style EcudoPlugin fill:#FFE4B5,stroke:#E8890C,color:#000
    style EODCPlugin fill:#FFE4B5,stroke:#E8890C,color:#000
    style BgeePlugin fill:#FFE4B5,stroke:#E8890C,color:#000
    style VipPlugin fill:#FFE4B5,stroke:#E8890C,color:#000
```

The plugin contract is intentionally minimal — only
`iterate_datasets` and `process` are abstract. The remaining
lifecycle methods (`setup`, `before_crawl`, `after_crawl`,
`run_context_name`) are optional hooks with sensible defaults.
The framework handles parallel execution, JSONL persistence,
progress display, run directories, and state management. See
[Writing Plugins](../guides/writing-plugins.md) for a step-by-step
guide.


## CrawlerPlugin

<sub>📄 `apps/crawlers/src/crawlers/core/plugin.py:128-269`</sub>

`CrawlerPlugin[RawT, ConfigT]` is the abstract base for all
plugins. The two type parameters define the plugin's data flow:

- **`RawT`** — the type yielded by `iterate_datasets()`. Ecudo
  yields `str` (dataset IDs requiring a detail fetch in
  `process()`), EODC yields `dict` (full STAC items), Bgee yields
  a custom `BgeeRawRecord`.
- **`ConfigT`** — the plugin's config class, which must extend
  [CrawlConfig](configuration.md#config-inheritance).

A concrete subclass sets three class attributes (`name`,
`description`, `config_class`) and implements two abstract methods
(`iterate_datasets`, `process`). The `crawl` command is
auto-registered when `name` is a string — no decorator needed.

### Command Registration

<sub>📄 `apps/crawlers/src/crawlers/core/plugin.py:36-90`</sub>

Commands are declared with the `@command` decorator on async
methods:

```python
@command
async def list_organizations(self, config: EcudoApiConfig, stack: AsyncExitStack) -> None:
    """List available organizations from Ecudo."""
    ...
```

The decorator infers the command name from the method
(`list_organizations` → `list-organizations`), the config class
from the first `ConfigBase`-typed parameter, and the help text
from the docstring. Override any of these with keyword arguments:
`@command(name="ls", help="...")`.

When a subclass is created, `__init_subclass__` scans all methods
for `_command_def` attributes and collects them into the class-level
`_commands` dict. Commands are inherited — a method decorated in a
parent class is available in all subclasses unless overridden.

### CLI Generation and Dispatch

<sub>📄 `apps/crawlers/src/crawlers/core/plugin.py:177-235`</sub>

From the collected commands, `register_args(parser)` builds the
full argparse structure — a global `-c / --config` option, a
subparser per command, and argument groups derived from each
command's config class hierarchy. At runtime, `run(cli_args)`
resolves the selected command, builds the config object from all
sources (see
[Configuration — Resolution Priority](configuration.md#resolution-priority)),
and invokes the decorated method with an `AsyncExitStack` for
resource cleanup.

For example, the generated `--help` for Ecudo shows how config
inheritance maps to argument groups:

```
$ crawlers ecudo crawl -h
usage: crawlers ecudo crawl [-h] [--page-size ...] [-n MAX_RECORDS] ...
                            organization

EcudoCrawlConfig:
  --page-size PAGE_SIZE Items per API page
  organization          Organization ID (e.g. iopan)

EcudoApiConfig:
  --base-url BASE_URL   Ecudo API base URL

HttpConfig:
  --timeout TIMEOUT     Request timeout in seconds
  --max-retries MAX_RETRIES
                        Maximum retry attempts

CrawlConfig:
  --no-url-validation   Disable HEAD-probe URL validation during parse
  -n MAX_RECORDS, --max-records MAX_RECORDS
                        Maximum number of items to fetch

OutputConfig:
  -o OUTPUT_DIR, --output-dir OUTPUT_DIR
                        Output directory for crawled data

ProcessingConfig:
  --concurrency CONCURRENCY
                        Number of concurrent workers
  --queue-size QUEUE_SIZE
                        Size of the processing queue
```

Each config class in the MRO becomes a separate argument group —
plugin-specific fields at the top, shared framework fields below.


## HttpClient

<sub>📄 `apps/crawlers/src/crawlers/core/http.py:66-314`</sub>

Both `iterate_datasets()` and `process()` typically need to make
HTTP calls — for API pagination, detail fetches, or URL validation.
[**HttpClient**](glossary.md#httpclient) is the async HTTP client
all plugins use for this. It provides retries with exponential
backoff, `Result`-based error handling, and session management via
async context manager.

```python
async with HttpClient(base_url="https://api.example.com", timeout=15) as http:
    result = await http.get_json("/items")
    match result:
        case Ok(data):  ...
        case Err(failure):  ...
```

Plugins typically create an `HttpClient` in
[`setup()`](#crawl-lifecycle) using `HttpClient.from_config(config)`
and register it on the `AsyncExitStack` for automatic cleanup:

```python
async def setup(self, ctx, stack):
    self._http = await stack.enter_async_context(
        HttpClient.from_config(ctx.config)
    )
```

### Request Methods

The client offers typed convenience methods — all returning
`Result[T, HttpFailure]`:

| Method | Returns | Use |
|--------|---------|-----|
| `get_json(url)` | `Result[JsonValue, ...]` | JSON API calls |
| `post_json(url, body)` | `Result[JsonValue, ...]` | POST with JSON body |
| `get_json_object(url)` | `Result[JsonObject, ...]` | JSON guaranteed to be a dict |
| `get_text(url)` | `Result[str, ...]` | Text responses |
| `get_bytes(url)` | `Result[bytes, ...]` | Binary responses |
| `head(url)` | `Result[None, ...]` | URL reachability checks |

### Error Types

<sub>📄 `apps/crawlers/src/crawlers/core/http.py:29-63`</sub>

Non-200 responses produce `ResponseFailure` (with status code,
method, URL, and truncated body). Network/timeout errors after
exhausting retries produce `TimeoutFailure`. Both carry `to_json()`
for structured serialization into rejection records.

### URL Resolution

When `base_url` is set, relative URLs are resolved against it.
Absolute URLs pass through unchanged — useful for server-provided
pagination links that may point to a different host.


## Iteration and Processing

<sub>📄 `apps/crawlers/src/crawlers/core/plugin.py:253-269`</sub>

Once the CLI dispatches a crawl command and config is loaded, the
framework calls the plugin's two core methods — the only abstract
methods on `CrawlerPlugin`:

```python
@abstractmethod
async def iterate_datasets(self, ctx: RunContext[ConfigT]) -> AsyncIterator[RawT]:
    """Async-iterate raw items from the upstream API."""

@abstractmethod
async def process(self, raw: RawT, /) -> Result[OnedataDataset, Any] | None:
    """Convert a raw item into an OnedataDataset."""
```

- **`iterate_datasets(ctx)`** — yields raw items from the upstream
  API. This is the producer side of the
  [parallel execution](#parallel-execution) model — the framework
  feeds these items into a bounded `asyncio.Queue`.

- **`process(raw)`** — converts a single raw item into an
  `OnedataDataset`. Runs inside one of N concurrent workers. May
  do I/O (additional API calls via the
  [HttpClient](#httpclient) stored on `self`, URL validation).
  Return:
  - `Ok(dataset)` — persisted to `processed.jsonl`
  - `Err(failure)` — persisted to `rejected.jsonl` with failure
    details
  - `None` — silently skipped (not counted as rejection)

The split between iteration and processing is the core design
choice: `iterate_datasets` handles pagination and listing,
`process` handles the per-item work (fetching details, parsing,
building metadata, assembling the
[OnedataDataset](#onedatadataset-assembly)). Because `process`
runs in parallel workers, it must be safe for concurrent
execution — store shared resources (like `HttpClient`) on `self`
during [`setup()`](#crawl-lifecycle), but avoid shared mutable
state.


## OnedataDataset Assembly

<sub>📄 `apps/crawlers/src/crawlers/model/dataset.py:91-163`</sub>

Inside `process()`, after parsing raw data and constructing a
[metadata record](metadata.md), the plugin calls
`OnedataDataset.build()` — the factory method that validates
inputs and produces the final registration-ready dataset.

```mermaid
graph TB
    PROC["⚙️ plugin.process(raw)"]

    subgraph Build["OnedataDataset.build()"]
        CHK1{"files\nnon-empty?"}
        CHK2{"paths\nunique?"}
        CHK3{"URLs\nreachable?"}
        XML["metadata.to_xml()"]
        OK["Ok(OnedataDataset)"]
    end

    PROC --> Build
    CHK1 -->|yes| CHK2
    CHK1 -->|no| ERR1["Err·NoFilesFailure·"]
    CHK2 -->|yes| CHK3
    CHK2 -->|no| ERR2["Err·DuplicatePathsFailure·"]
    CHK3 -->|yes| XML --> OK
    CHK3 -->|no| ERR3["Err·InvalidUrlFailure·"]

    classDef process fill:#4ECDC4,stroke:#0B7285,color:#000
    classDef check fill:#FFD700,stroke:#F08C00,color:#000
    classDef success fill:#95D5B2,stroke:#2D6A4F,color:#000
    classDef error fill:#E63946,stroke:#9D0208,color:#fff

    class PROC process
    class CHK1,CHK2,CHK3 check
    class XML,OK success
    class ERR1,ERR2,ERR3 error
```

The build method performs three validations before producing the
dataset:

1. **Non-empty files** — datasets with no downloadable files are
   rejected with `NoFilesFailure`.
2. **Unique paths** — duplicate `OnedataFile.path` values are
   rejected with `DuplicatePathsFailure`. Plugins handle path
   deduplication in their parsers (e.g.
   `resolve_path_collisions()`).
3. **URL reachability** (optional) — when an `HttpClient` is
   provided, all file URLs are probed in parallel via HEAD requests.
   Any unreachable URL rejects the dataset with
   `InvalidUrlFailure`. Controlled by the `--no-url-validation`
   flag.

If all validations pass, `metadata.to_xml()` is called eagerly to
materialize the XML string. The resulting `OnedataDataset` is a
frozen dataclass carrying `name`, `location`, `pid`,
`metadata_xml`, and `files` — fully self-contained and ready for
serialization to `processed.jsonl`.

### Typical process() Pattern

Every plugin's `process()` method follows the same shape: parse raw
data, construct a metadata record, call `OnedataDataset.build()`:

```python
async def process(self, raw: dict, /) -> Result[OnedataDataset, Any] | None:
    parsed = parse_item(raw)
    if parsed is None:
        return None

    return await OnedataDataset.build(
        pid=parsed.identifier,
        name=parsed.title,
        location=parsed.title.replace("/", "-"),
        metadata=parsed.metadata,      # OpenAIRERecord or DataCiteRecord
        files=[OnedataFile(path=f.path, url=f.url) for f in parsed.files],
        http=self._validation_http,     # None to skip URL checks
    )
```


## Crawl Lifecycle

<sub>📄 `apps/crawlers/src/crawlers/core/plugin.py:277-322`</sub>

The sections above describe what a plugin provides — now here's the
full sequence of how the framework orchestrates a crawl from start
to finish. `run_crawl(config)` drives this in a fixed order:

```mermaid
sequenceDiagram
    participant P as 🔌 CrawlerPlugin
    participant CTX as 📁 RunContext
    participant R as ⚙️ run_parallel_crawl

    P->>CTX: _create_run_context(config)
    P->>CTX: ctx.open(config_snapshot)
    Note over P: 🖨️ _print_banner()

    P->>P: setup(ctx, stack)
    P->>P: before_crawl(ctx)

    P->>R: run_parallel_crawl(iterator, process_fn, sinks)
    R-->>P: CrawlStats

    alt ✅ normal
        P->>P: after_crawl(ctx)
        P->>P: status = "completed"
    else ⏹️ interrupted
        P->>P: status = "interrupted"
    else ❌ exception
        P->>P: status = "failed"
    end

    Note over P: 🔚 finally
    P->>CTX: ctx.close(status)
    Note over P: 🖨️ _print_summary()
```

1. **`_create_run_context(config)`** — creates a
   [RunContext](#workspace-and-run-management) with a timestamped
   run directory.
2. **`ctx.open()`** — creates the directory, writes `config.json`,
   opens JSONL sinks.
3. **`setup(ctx, stack)`** — plugin hook for opening resources
   (HTTP clients, API facades). Register async context managers on
   `stack` so they close automatically on exit.
4. **`before_crawl(ctx)`** — plugin hook for pre-crawl validation
   (e.g. checking that a requested organization exists).
5. **`run_parallel_crawl(...)`** — the parallel execution step
   detailed [below](#parallel-execution).
6. **`after_crawl(ctx)`** — plugin hook for post-run actions
   (e.g. printing a conformity check).
7. **`ctx.close(status)`** — closes sinks, writes final
   `state.json`.

On `KeyboardInterrupt` or `CancelledError`, status is set to
`"interrupted"`. On other exceptions, status is `"failed"` and the
exception re-raises after cleanup. The `AsyncExitStack` ensures all
resources opened during `setup()` are cleaned up regardless of
outcome.

### Lifecycle Hooks

| Hook | When | Example |
|------|------|---------|
| `setup(ctx, stack)` | Before crawl starts | Open HTTP clients |
| `before_crawl(ctx)` | After setup, before workers | Validate preconditions |
| `after_crawl(ctx)` | After workers finish | Post-run reporting |
| `run_context_name(config)` | Run directory creation | Customize suffix |


## Parallel Execution

<sub>📄 `apps/crawlers/src/crawlers/core/runner.py:52-140`</sub>

Step 5 of the lifecycle above — `run_parallel_crawl()` — is where
the actual dataset processing happens. It drives the crawl with a
producer–consumer pattern:

```mermaid
graph LR
    subgraph Producer
        SRC["🌐 iterate_datasets"]
    end

    SRC -->|item| Q[("📬 asyncio.Queue\nbounded")]

    subgraph "⚙️ N Workers"
        W1["⚙️ Worker 1\nprocess·item·"]
        WN["⚙️ Worker N\nprocess·item·"]
    end

    Q --> W1
    Q --> WN

    W1 & WN -->|"Ok(dataset)"| PS["💾 processed.jsonl"]
    W1 & WN -->|"Err(failure)"| RS["❌ rejected.jsonl"]
    W1 & WN -->|None| SK["⏭️ skipped"]
    W1 & WN -->|exception| FL["⚠️ failed"]

    SRC -.->|None sentinel ×N| Q

    classDef external fill:#A8DADC,stroke:#1864AB,color:#000
    classDef internal fill:#4ECDC4,stroke:#0B7285,color:#000
    classDef success fill:#95D5B2,stroke:#2D6A4F,color:#000
    classDef warning fill:#FFD700,stroke:#F08C00,color:#000
    classDef error fill:#E63946,stroke:#9D0208,color:#fff
    classDef data fill:#E6E6FA,stroke:#5B4B8A,color:#000

    class SRC external
    class Q data
    class W1,WN internal
    class PS success
    class SK warning
    class FL,RS error
```

1. A **producer** task pulls from `iterate_datasets()` and enqueues
   items into a bounded `asyncio.Queue`.
2. **N worker** tasks (configurable via `concurrency`, default 128)
   dequeue items and call `process(item)`.
3. Workers route results: `Ok(dataset)` → processed sink,
   `Err(failure)` → rejection sink, `None` → skip counter,
   exceptions → failure counter with warning.
4. Every `state_save_interval` items (default 100), stats are
   persisted to `state.json`.
5. The producer sends `None` sentinels (one per worker) to signal
   completion.
6. A Rich progress bar shows live throughput.

The bounded queue creates natural backpressure — the producer
blocks when the queue is full (`queue_size`, default 1000),
preventing unbounded memory growth against a fast API.

### CrawlStats

<sub>📄 `apps/crawlers/src/crawlers/core/runner.py:33-48`</sub>

The runner tracks five counters: `queued`, `processed`, `rejected`,
`skipped`, and `failed`. These feed both the periodic state
persistence and the post-crawl summary display.


## Workspace and Run Management

<sub>📄 `apps/crawlers/src/crawlers/core/workspace.py:22-91`</sub>

All the output from parallel execution — processed datasets,
rejected items, crawl statistics — lands in a **run directory**
with a fixed structure, managed by
[**RunContext**](glossary.md#runcontext):

```
<workspace>/runs/<timestamp>_<plugin>_<context>/
  config.json       # Config snapshot at run start
  state.json        # Status, timestamps, running stats
  processed.jsonl   # Successfully built OnedataDatasets
  rejected.jsonl    # Rejected items with failure details
```

`RunContext` manages the directory lifecycle:

1. **`open(config_snapshot)`** — creates the directory, writes
   `config.json`, initializes `state.json` with status `"running"`,
   opens both JSONL sink instances.
2. **`save_stats(stats)`** — periodically updates `state.json`
   (called by the runner every 100 items).
3. **`close(status)`** — closes sinks, writes final `state.json`
   with status `"completed"`, `"interrupted"`, or `"failed"`.


## Display

<sub>📄 `apps/crawlers/src/crawlers/core/plugin.py:426-484`</sub>

After the crawl completes, `CrawlerPlugin` uses Rich to present
a summary automatically — no plugin code needed. The output has
three phases:

- **Banner** — plugin class name, run context name, run directory
  path.
- **Progress** — live Rich progress bar during parallel execution.
- **Summary** — crawl statistics table, output file paths, and
  next-step suggestions (including a registrar command if records
  were processed, and a pointer to `rejected.jsonl` if items were
  rejected).


## Plugin Registry

<sub>📄 `apps/crawlers/src/crawlers/plugins/__init__.py:1-25` · `apps/crawlers/src/crawlers/cli.py:52-68`</sub>

The [CLI generation](#cli-generation-and-dispatch) section above
showed how a single plugin's commands become argparse subcommands —
but how does the CLI discover plugins in the first place? Plugins
are registered as a hardcoded list in
`apps/crawlers/src/crawlers/plugins/__init__.py`. The CLI entry point iterates this
list, creates an argparse subparser per plugin (using
`plugin.name`), and calls `plugin.register_args()`. At runtime,
the selected plugin's `run()` method is invoked via
`asyncio.run()`.

There is no dynamic plugin discovery — the registry is
intentionally simple because adding a plugin to the list is
trivial. See
[Writing Plugins — Step 5](../guides/writing-plugins.md#step-5-register-the-plugin)
for how to register a new plugin.
