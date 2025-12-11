# eCUDO Crawler Architecture

This document describes the modular architecture of the eCUDO crawler.

## Overview

The crawler is designed with clear separation of concerns, making it easy to:
- Add new data sources (by creating new parsers)
- Add new metadata formats (by creating new serializers)
- Modify processing logic (by adding/removing processors)
- Scale horizontally (via the parallel fetcher)

## Module Structure

```
ecudo/
├── __init__.py           # Package exports and version
├── __main__.py           # CLI entry point
├── cli.py                # Command-line interface (CLI commands)
├── crawler.py            # EcudoCrawler - high-level orchestration
├── config.py             # Configuration management
├── output.py             # Logging utilities
│
├── ecudo_api/            # Low-level eCUDO API client
│   ├── client.py         # EcudoClient - HTTP requests
│   └── iterator.py       # RecordIDIterator - ID pagination
│
├── models/               # Data structures
│   ├── ecudo.py         # EcudoDataset, FileInfo
│   └── onedata.py        # OnedataDataset, OnedataFile
│
├── parsers/              # Input parsing
│   └── ecudo.py          # JSON-LD → EcudoDataset
│
├── metadata/             # Metadata format generators
│   └── openaire.py       # OpenAIRE XML generator (functional)
│
├── processors/           # Pipeline processors
│   ├── base.py           # Processor[I, O] ABC
│   ├── fetchers.py       # MetadataFetcher
│   ├── validators.py     # URLValidator
│   ├── filters.py        # DiversityFilter
│   ├── converters.py     # OnedataConverter
│   ├── pipeline.py       # ProcessorPipeline
│   └── writers.py        # JSONLWriter
│
└── orchestration/        # Parallel processing
    └── parallel.py       # run_parallel_pipeline() function
```

## Data Flow

The entire crawl is expressed as a single pipeline:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           Processing Pipeline                                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   ┌───────────────────┐                                                         │
│   │  RecordIDIterator │  Lightweight: fetches only record IDs                   │
│   │  (sequential)     │                                                         │
│   └────────┬──────────┘                                                         │
│            │ yields IDs (str)                                                   │
│            ▼                                                                    │
│   ┌──────────────────────────────────────────────────────────────────────────┐  │
│   │                 run_parallel_pipeline() (N workers)                      │  │
│   │                                                                          │  │
│   │   ┌──────────────────────────────────────────────────────────────────┐   │  │
│   │   │                    ProcessorPipeline                             │   │  │
│   │   │                                                                  │   │  │
│   │   │   ┌────────────────┐                                             │   │  │
│   │   │   │ DatasetFetcher │  ID → fetch JSON-LD → parse → EcudoDataset  │   │  │
│   │   │   └───────┬────────┘                                             │   │  │
│   │   │           │ EcudoDataset                                         │   │  │
│   │   │           ▼                                                      │   │  │
│   │   │   ┌────────────────┐                                             │   │  │
│   │   │   │  URLValidator  │  Validates all file URLs (optional)         │   │  │
│   │   │   └───────┬────────┘                                             │   │  │
│   │   │           │ EcudoDataset                                         │   │  │
│   │   │           ▼                                                      │   │  │
│   │   │   ┌────────────────┐                                             │   │  │
│   │   │   │DiversityFilter │  Limits similar datasets (optional)         │   │  │
│   │   │   └───────┬────────┘                                             │   │  │
│   │   │           │ EcudoDataset                                         │   │  │
│   │   │           ▼                                                      │   │  │
│   │   │   ┌────────────────┐                                             │   │  │
│   │   │   │  JSONLWriter   │  Saves _raw JSON to JSONL (pass-through)    │   │  │
│   │   │   └───────┬────────┘                                             │   │  │
│   │   │           │ EcudoDataset                                         │   │  │
│   │   │           ▼                                                      │   │  │
│   │   │   ┌────────────────┐                                             │   │  │
│   │   │   │OnedataConverter│  EcudoDataset → OnedataDataset + XML        │   │  │
│   │   │   └───────┬────────┘                                             │   │  │
│   │   │           │ OnedataDataset                                       │   │  │
│   │   │           ▼                                                      │   │  │
│   │   │   ┌────────────────┐                                             │   │  │
│   │   │   │  JSONLWriter   │  Saves final output                         │   │  │
│   │   │   └────────────────┘                                             │   │  │
│   │   │                                                                  │   │  │
│   │   └──────────────────────────────────────────────────────────────────┘   │  │
│   │                                                                          │  │
│   └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Key Components

### EcudoClient (`ecudo_api/client.py`)

Low-level HTTP client for eCUDO API. Handles:
- Session management (async context manager)
- Retries with exponential backoff
- JSON fetching
- URL validation (HEAD requests)

```python
async with EcudoClient() as client:
    orgs = await client.get_organizations()
    metadata = await client.get_dataset_metadata(record_id)
```

### EcudoDatasetIDIterator (`ecudo_api/iterator.py`)

Async iterator that yields record IDs from an organization. Lightweight - fetches
only IDs (small payloads), not full metadata. This allows the heavy metadata
fetching to be parallelized by workers.

```python
async with EcudoClient() as client:
    iterator = EcudoDatasetIDIterator(client, "iopan", max_records=100)
    async for record_id in iterator:
        # record_id is fed to the pipeline
        pass
```

### EcudoDataset (`models/ecudo.py`)

Structured representation of a dataset. eCUDO-specific for now, but designed
to be easily extended when other data sources are added.

### OnedataDataset (`models/onedata.py`)

Output structure ready for Onedata registration:

### Processor[I, O] (`processors/base.py`)

Generic typed processor base class. Processors can:
- Transform data (`I` → `O`)
- Filter data (return `None` to skip)
- Have lifecycle methods (`open()`, `close()`)
- Report statistics (`get_stats()`)

```python
class MyProcessor(Processor[EcudoDataset, EcudoDataset]):
    async def process(self, record: EcudoDataset) -> EcudoDataset | None:
        if not self.is_valid(record):
            return None  # Filter out
        return record  # Pass through
    
    def get_stats(self) -> dict:
        return {"processed": self._count}
```

### ProcessorPipeline (`processors/pipeline.py`)

Chains multiple processors into a sequential pipeline:

```python
pipeline = ProcessorPipeline([
    DatasetFetcher(...),
    URLValidator(...),
    DiversityFilter(...),
    OnedataConverter(serializer),
    JSONLWriter(processed_output),
])

await pipeline.open()
result = await pipeline.process(record_id)  # Flows through all processors
await pipeline.close()

# Aggregate stats from all processors
stats = pipeline.get_stats()
```

## Parallel fetcher (`orchestration/parallel.py`)

`run_parallel_pipeline` implements the producer-consumer loop used by the CLI.
It separates lightweight ID iteration from heavy metadata processing and applies
backpressure via a bounded queue.

Key behaviors:
- Configurable `concurrency` and `queue_size` for workers and backpressure.
- `ProcessingStats` tracks queued, processed, and failed items.
- Errors per item are logged as warnings; processing continues for other items.
- Uses `None` sentinels to stop workers cleanly once the producer finishes.

Example:
```python
stats = await run_parallel_pipeline(
    dataset_id_source=record_id_iterator,
    dataset_pipeline=pipeline,
    concurrency=128,
    queue_size=1000,
)
```

### Built-in Processors

| Processor          | Input | Output | Description |
|--------------------|-------|--------|-------------|
| `DatasetFetcher`   | `str` (ID) | `EcudoDataset` | Fetches JSON-LD and parses |
| `URLValidator`     | `EcudoDataset` | `EcudoDataset` | Validates file URLs |
| `DiversityFilter`  | `EcudoDataset` | `EcudoDataset` | Limits similar titles |
| `OnedataConverter` | `EcudoDataset` | `OnedataDataset` | Builds Onedata output |
| `JSONLWriter`      | `T` | `T` | Writes to JSONL file |

## Configuration

Configuration uses a three-layer hierarchy (higher overrides lower):
1. CLI arguments
2. Config file (`ecudo.yaml`)
3. Environment variables (`ECUDO_*` prefix)

See `config.example.yaml` for all options.

## Extending the Crawler

### Adding a New Processor

1. Create processor class:

```python
from ecudo.processors.base import Processor
from ecudo.models import EcudoDataset


class MyFilter(Processor[EcudoDataset, EcudoDataset]):
    def __init__(self, threshold: float):
        self.threshold = threshold
        self._filtered = 0

    async def process(self, record: EcudoDataset) -> EcudoDataset | None:
        if self.should_skip(record):
            self._filtered += 1
            return None
        return record

    def get_stats(self) -> dict:
        return {"filtered": self._filtered}
```

2. Add to pipeline in `crawler.py`

## Performance Considerations

- **Concurrency**: Default 128 workers. Adjust based on target API rate limits.
- **Queue size**: 1000 items. Provides backpressure.
- **Page size**: 200 IDs per page. eCUDO API default.
- **Timeout**: 15 seconds per request.
- **Retries**: 3 attempts with exponential backoff.

## Testing

Run a small test crawl:
```bash
python -m ecudo crawl iopan -n 10 --no-url-validation
```

Run with quiet mode:
```bash
python -m ecudo -q crawl iopan -n 100
```

Check output:
```bash
python -m ecudo convert data/iopan_processed.jsonl
cat data/iopan_processed.json | jq '.[0]'
```

Run unit tests:
```bash
python -m pytest tests/ -v
```
