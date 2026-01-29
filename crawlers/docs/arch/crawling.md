# Crawling System

## Overview

The crawling system orchestrates the entire data collection process. It consists of:

- **ApiClient**: Base class for HTTP communication with external APIs
- **BaseCrawler**: Orchestrates the crawl lifecycle (client, pipeline, parallel execution)
- **Parallel execution**: Concurrent processing with progress tracking

The framework handles common concerns (HTTP retries, session management, progress display, 
error handling) while plugins provide API-specific logic.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          BaseCrawler                                │
├─────────────────────────────────────────────────────────────────────┤
│  run()                                                              │
│    │                                                                │
│    ├─► _print_banner()                                              │
│    │                                                                │
│    ├─► create_client() ──────────► ApiClient                        │
│    │                                  │                             │
│    ├─► before_crawl(client) ◄─────────┤                             │
│    │                                  │                             │
│    ├─► build_pipeline(client) ──► ProcessorPipeline                 │
│    │                                                                │
│    ├─► pipeline.open()                                              │
│    │                                                                │
│    ├─► create_iterator(client) ──► AsyncIterable[T]                 │
│    │                                  │                             │
│    ├─► run_parallel_pipeline() ◄──────┤                             │
│    │       │                                                        │
│    │       ├─► Producer (iterator → queue)                          │
│    │       └─► Workers (queue → pipeline.process())                 │
│    │                                                                │
│    ├─► pipeline.close()                                             │
│    │                                                                │
│    ├─► after_crawl()                                                │
│    │                                                                │
│    └─► _print_summary()                                             │
└─────────────────────────────────────────────────────────────────────┘
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
        self._session: aiohttp.ClientSession | None = None
```

**Type Parameters:**

| Parameter | Description |
|-----------|-------------|
| `OptsT` | Iterator options type (e.g., `EcudoIteratorOpts`) |
| `DatasetT` | Type yielded by iterator (e.g., `str` for IDs, `dict` for JSON) |

### Context Manager

ApiClient must be used as async context manager:

```python
async with EcudoClient(base_url="http://api.example.com") as client:
    # Session is active here
    data = await client.get_json("/endpoint")
# Session is closed
```

### Built-in HTTP Methods

```python
# GET JSON with retries
data = await client.get_json(url)

# POST JSON with retries
response = await client.post_json(url, body={"key": "value"})

# Validate URL accessibility (HEAD request)
is_valid = await client.validate_url(url)
```

**Retry behavior:**
- Exponential backoff: 2s, 4s, 8s...
- Logs warnings on retries
- Returns empty dict `{}` on failure (doesn't raise)

### Abstract Method

Every client must implement `iterate_datasets()`:

```python
@abstractmethod
def iterate_datasets(self, opts: OptsT) -> AsyncIterator[DatasetT]:
    """Iterate over datasets."""
```

## BaseCrawler

### Base Class

```python
class BaseCrawler[ConfigT: BaseCrawlConfig](ABC):
    """Abstract base class for crawlers."""
    
    def __init__(self, config: ConfigT):
        self.config = config
        self.stats: CrawlStats | None = None
        self.interrupted = False
        self._pipeline: ProcessorPipeline | None = None
```

### Optional Hooks

```python
async def before_crawl(self, client: ApiClient) -> None:
    """Pre-crawl validation (e.g., check organization exists)."""

async def after_crawl(self) -> None:
    """Post-crawl processing (called only on success)."""

def get_max_items(self) -> int | None:
    """Return max items for progress tracking. None = unknown total."""

def _get_banner_subtitle(self) -> str | None:
    """Banner subtitle (e.g., organization name)."""
```

## Parallel Execution

### run_parallel_pipeline

Executes pipeline concurrently with progress tracking:

```python
async def run_parallel_pipeline[InT, OutT](
    source_iterator: AsyncIterable[InT],
    pipeline: ProcessorPipeline[InT, OutT],
    *,
    concurrency: int = 10,      # Number of workers
    queue_size: int = 1000,     # Buffer size
    max_items: int | None = None,  # For progress bar
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
- Progress bar shows live status
- Graceful shutdown on Ctrl+C

## Best Practices

### Client Implementation

- Use `get_json()` / `post_json()` for automatic retries
- Log pagination progress with `console.info()`
- Check `max_items` limit and return early
- Implement `get_collections()` or similar for validation

### Crawler Implementation

- Call `super().__init__(config)` in constructor
- Create output directories in `__init__`
- Use `cast()` to get typed client from `ApiClient`
- Implement `before_crawl()` for validation
- Override `get_max_items()` for progress bar
- Override `_get_banner_subtitle()` for context

### Iterator Design

Choose pattern based on API:

| API Design | Iterator Yields | First Processor |
|------------|-----------------|-----------------|
| List IDs, fetch details | `str` (ID) | `DatasetFetcher` |
| Search returns full records | `dict` (record) | `ParserProcessor` |

### Error Handling

- `ApiClient` returns `{}` on failure (doesn't raise)
- Check for empty responses in iterator
- Pipeline handles `None` from processors (filtering)
- Ctrl+C is caught, summary still prints

### Progress Tracking

```python
def get_max_items(self) -> int | None:
    # Return max_records for determinate progress bar
    # Return None for indeterminate progress (spinner)
    return self.config.max_records
```
