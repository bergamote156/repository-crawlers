# Crawling System

## Overview

The crawling system orchestrates the entire data collection process. It consists of:

- **ApiClient**: Base class for HTTP communication with external APIs
- **DefaultCrawlerPlugin**: Orchestrates the crawl lifecycle via `prepare_crawl()`
- **RunContext**: Manages the run directory, state persistence, and sink lifecycle
- **Parallel execution**: Concurrent processing with progress tracking

The framework handles common concerns (HTTP retries, session management, progress
display, run persistence) while plugins provide API-specific logic through `CrawlSpec`.

## Architecture

```
DefaultCrawlerPlugin.run_crawl(config)
    │
    ├─► prepare_crawl(config)              [plugin implements]
    │       └─► returns CrawlSpec
    │               (client, iterator_opts, parser, metadata_builder, ...)
    │
    ├─► RunContext.open(config_snapshot)
    │       ├─ creates run directory
    │       ├─ saves config.json
    │       └─ opens sinks (raw, processed, rejected)
    │
    ├─► async with spec.client:
    │       │
    │       ├─► before_crawl(spec)         [plugin hook, optional]
    │       │
    │       ├─► build_pipeline(spec, ctx)  [framework default or plugin override]
    │       │
    │       ├─► run_parallel_pipeline()
    │       │       ├─► Producer (iterator → queue)
    │       │       └─► Workers (queue → pipeline → sinks)
    │       │
    │       └─► after_crawl()              [plugin hook, optional]
    │
    └─► RunContext.close(status)
            ├─ saves final state.json
            └─ closes sinks
```

## ApiClient

### Base Class

```python
class ApiClient[OptsT, DatasetT](ABC):
    """Base API client with built-in HTTP handling."""

    def __init__(
        self,
        base_url: str,
        timeout: int = 15,
        max_retries: int = 3,
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
```

**Type Parameters:**

| Parameter | Description |
|-----------|-------------|
| `OptsT` | Iterator options type (e.g., `EcudoIteratorOpts`) |
| `DatasetT` | Type yielded by iterator (e.g., `str` for IDs, `dict` for JSON records) |

### Context Manager

`ApiClient` must be used as an async context manager. The framework opens the
session automatically — plugin code only interacts with the client inside `before_crawl()`.

```python
# Framework opens/closes the session:
async with spec.client:
    await self.before_crawl(spec)
    # ...

# Inside before_crawl, client is already open:
async def before_crawl(self, spec: CrawlSpec) -> None:
    client = cast(MyClient, spec.client)
    result = await client.get_json("/validate")
```

### Built-in HTTP Methods

All HTTP methods return `Result[T, ApiError]`.

```python
# GET JSON with retries
match await client.get_json(url):
    case Ok(data):
        process(data)
    case Err(HttpError(status=404)):
        skip()
    case Err(err):
        log(err)

# POST JSON with retries
result = await client.post_json(url, body={"key": "value"})

# Validate URL accessibility (HEAD request)
result = await client.validate_url(url)

# Transform Ok values — Err passes through unchanged
result = (await client.get_json(url)).map(lambda d: d.get("items", []))
```

**Retry behavior:**
- Exponential backoff: 2s, 4s, 8s...
- Returns `Err(HttpTimeoutError(...))` after all attempts exhausted
- Returns `Err(HttpError(...))` on non-2xx status (no retry)

### Abstract Method

Every client must implement `iterate_datasets()`:

```python
@abstractmethod
def iterate_datasets(self, opts: OptsT) -> DatasetIterator[DatasetT]:
    """Create a dataset iterator."""
```

## DatasetIterator

Defined in `crawlers.core.abc.api`. Each call to `iterate_datasets()` returns
a new iterator with its own isolated state.

```python
class DatasetIterator[DatasetT](ABC):
    def __aiter__(self) -> Self: ...
    async def __anext__(self) -> DatasetT: ...
```

**Iteration patterns:**

| API Design | Iterator yields | First processor |
|------------|-----------------|-----------------|
| Listing returns IDs, details fetched separately | `str` (ID) | `DatasetFetcher` |
| Search returns full records | `dict` (record) | `ParserProcessor` |

## CrawlSpec

`CrawlSpec` is the description of a crawl run, returned by `prepare_crawl()`.
The framework consumes it to drive execution — the plugin only needs to fill it in.

```python
@dataclass
class CrawlSpec:
    # Required
    client: ApiClient              # API client (session managed by framework)
    iterator_opts: object          # Passed to client.iterate_datasets(opts)
    parser: Parser                 # Transforms raw API items to dataset models
    metadata_builder: MetadataBuilder  # Produces metadata XML

    # Optional
    run_context_name: str = "default"  # Used in run directory name
    banner_subtitle: str | None = None # Shown in startup banner
    max_items: int | None = None       # Cap + enables progress bar
    url_validation: bool = True        # Whether to run URLValidator
```

## DefaultCrawlerPlugin

The main base class for plugin implementations. Subclass and implement
`prepare_crawl()` — the framework handles everything else.

```python
class DefaultCrawlerPlugin(CrawlerPlugin):
    name: str
    description: str
    config_class: type[DefaultCrawlConfig] = DefaultCrawlConfig

    @abstractmethod
    def prepare_crawl(self, config: DefaultCrawlConfig) -> CrawlSpec:
        """Describe the crawl. Called once before the client session opens."""
        ...

    async def before_crawl(self, spec: CrawlSpec) -> None:
        """Hook: validate state after client session is open."""

    async def after_crawl(self) -> None:
        """Hook: called after successful completion."""

    def build_pipeline(self, spec: CrawlSpec, ctx: DefaultRunContext) -> ProcessorPipeline:
        """Override to customize the pipeline. Default builds the standard pipeline."""
```

**Auto-registered `crawl` command:**

Defining `name` on a `DefaultCrawlerPlugin` subclass automatically registers a
`crawl` CLI command wired to `run_crawl()`. No `@command` decorator needed for
the main crawl command.

**Default pipeline** (built by `build_pipeline` unless overridden):

```
ParserProcessor → URLValidator → Tap(raw) → OnedataConverter → Tap(processed)
```

Rejection from any processor flows to `ctx.rejection_sink`.

## RunContext

Manages the run directory, state file, config snapshot, and sink lifecycle.

### Base Class (`core.abc.workspace`)

```python
class RunContext(ABC):
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir

    async def open(self, config_snapshot: dict | None = None) -> None:
        """Create directory, save config.json, set state=running, open sinks."""

    async def save_stats(self, stats: dict) -> None:
        """Persist current stats to state.json. Called periodically."""

    async def close(self, status: str = "completed") -> None:
        """Close sinks, write final state.json."""

    @abstractmethod
    async def open_sinks(self) -> None: ...

    @abstractmethod
    async def close_sinks(self) -> None: ...
```

### DefaultRunContext (`core.default.workspace`)

Standard implementation with three sinks:

```python
class DefaultRunContext(RunContext):
    raw_sink: Sink        # raw.jsonl  — raw parsed datasets
    processed_sink: Sink  # processed.jsonl — final Onedata datasets
    rejection_sink: Sink  # rejected.jsonl  — items rejected with reasons
```

### Run Directory Structure

```
<output_dir>/runs/<timestamp>_<plugin>_<context>/
    config.json       # Full config snapshot (immutable record of what ran)
    state.json        # Run status, timestamps, and stats
    raw.jsonl         # Raw parsed datasets (source models)
    processed.jsonl   # Final Onedata datasets
    rejected.jsonl    # Rejected items with reasons
```

`state.json` format:

```json
{
  "status": "completed",
  "started_at": "2026-03-27T14:30:00+00:00",
  "updated_at": "2026-03-27T14:35:12+00:00",
  "stats": {
    "queued": 2400,
    "processed": 2100,
    "filtered": 180,
    "failed": 120
  }
}
```

Status values: `running`, `completed`, `interrupted`, `failed`.

### make_run_dir()

```python
def make_run_dir(workspace: Path, plugin: str, context: str) -> Path:
    """
    Generate: <workspace>/runs/<timestamp>_<plugin>_<context>
    Timestamp uses dashes instead of colons for filesystem compatibility.
    """
```

## Parallel Execution

### run_parallel_pipeline

```python
async def run_parallel_pipeline[InT, OutT](
    source_iterator: AsyncIterable[InT],
    pipeline: ProcessorPipeline[InT, OutT],
    *,
    concurrency: int = 10,
    queue_size: int = 1000,
    max_items: int | None = None,
    state_callback: Callable[[CrawlStats], Awaitable[None]] | None = None,
    state_save_interval: int = 100,
) -> CrawlStats:
```

**Architecture:**

```
┌──────────────┐     ┌─────────────────┐     ┌───────────────┐
│   Iterator   │────▶│  Queue (buffer) │────▶│   Workers     │
│  (producer)  │     │   max 1000      │     │  (consumers)  │
└──────────────┘     └─────────────────┘     └───────────────┘
                                                    │
                                                    ▼
                                             ┌───────────────┐
                                             │   Pipeline    │
                                             │  process(x)   │
                                             └───────────────┘
```

**Behavior:**
- Producer reads from iterator, puts items in queue
- Workers take items from queue, run pipeline
- Live progress bar shown (determinate if `max_items` set, else spinner)
- `state_callback` invoked every `state_save_interval` processed items
- Graceful shutdown on Ctrl+C (status → `interrupted`)

### CrawlStats

```python
@dataclass
class CrawlStats:
    queued: int = 0      # Items pulled from iterator
    processed: int = 0   # Successfully through pipeline
    filtered: int = 0    # Rejected by processors
    failed: int = 0      # Worker errors
```

## Result Type

Defined in `crawlers.core.result`. Inspired by Erlang's `{ok, Val} | {error, Reason}`.

### Core Classes

```python
class Result[T, E](ABC):              # Base — never instantiate directly
class Ok[T](Result[T, Never]):        # Success variant
class Err[E](Result[Never, E]):       # Error variant
```

### Methods

| Method | `Ok(val)` | `Err(err)` |
|--------|-----------|------------|
| `is_ok()` | `True` | `False` |
| `is_err()` | `False` | `True` |
| `unwrap()` | returns `val` | raises `ValueError` |
| `unwrap_or(default)` | returns `val` | returns `default` |
| `err()` | raises `ValueError` | returns `err` |
| `map(fn)` | returns `Ok(fn(val))` | returns `self` unchanged |

### Pattern Matching (Python 3.10+)

```python
match await client.get_json(url):
    case Ok(data):
        process(data)
    case Err(HttpError(status=404)):
        handle_not_found()
    case Err(err):
        log(err)
```

### Structured Errors

Defined in `crawlers.core.errors`.

```python
type ApiError = HttpError | HttpTimeoutError

@dataclass(frozen=True)
class HttpError:
    status: int
    method: str
    url: str
    body: str = ""

@dataclass(frozen=True)
class HttpTimeoutError:
    method: str
    url: str
    attempts: int
    last_error: str
```

## Best Practices

### API Client Implementation

- Use `get_json()` / `post_json()` for automatic retries
- Log pagination progress with `console.info()`
- Respect `max_items` limit in the iterator
- Add helper methods for validation (e.g. `get_organizations()`)

### prepare_crawl Implementation

- Construct the `ApiClient` but don't open it (framework does that)
- Set `run_context_name` to something meaningful (e.g. organization ID, collection name)
- Set `max_items` from config for progress bar
- Set `url_validation` from config flag

### before_crawl Hook

- Use for pre-flight validation: check that an organization/collection exists
- The client session is already open — use `cast()` to get the typed client
- Call `sys.exit(1)` on validation failure

### build_pipeline Override

Override only when the default pipeline doesn't fit (e.g. need `DatasetFetcher`
instead of `ParserProcessor`, or want to add `DiversityFilter`):

```python
def build_pipeline(self, spec: CrawlSpec, ctx: DefaultRunContext) -> ProcessorPipeline:
    client = cast(MyClient, spec.client)
    return ProcessorPipeline(
        processors=[
            DatasetFetcher(fetch_fn=client.get_details, parser=spec.parser),
            URLValidator(validate_fn=client.validate_url, enabled=spec.url_validation),
            DiversityFilter(max_similar=10),
            Tap(ctx.raw_sink, transform=lambda d: d.to_json()),
            OnedataConverter(metadata_builder=spec.metadata_builder),
            Tap(ctx.processed_sink, transform=lambda d: d.to_json()),
        ],
        rejection_sink=ctx.rejection_sink,
    )
```
