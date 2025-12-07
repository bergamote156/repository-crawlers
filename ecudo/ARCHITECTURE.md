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
├── cli.py                # Command-line interface
├── config.py             # Configuration management
│
├── crawler/              # HTTP client and iterators
│   ├── client.py         # EcudoClient - low-level HTTP
│   └── iterator.py       # RecordIDIterator - ID pagination
│
├── models/               # Data structures
│   ├── record.py         # EcudoRecord, FileInfo
│   └── onedata.py        # OnedataDataset, OnedataFile
│
├── parsers/              # Input parsing
│   └── ecudo.py          # JSON-LD → EcudoRecord
│
├── serializers/          # Output serialization
│   ├── base.py           # MetadataSerializer ABC
│   └── openaire.py       # OpenAIRE XML serializer
│
├── processors/           # Pipeline processors
│   ├── base.py           # Processor[I, O] ABC
│   ├── fetchers.py       # MetadataFetcher
│   ├── validators.py     # URLValidator
│   ├── filters.py        # DiversityFilter
│   ├── converters.py     # OnedataConverter
│   ├── pipeline.py       # ProcessorPipeline
│   └── writers.py        # JSONLWriter, RawRecordWriter
│
└── orchestration/        # Parallel processing
    └── parallel.py       # ParallelFetcher
```

## Data Flow

The entire crawl is expressed as a single pipeline:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Processing Pipeline                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────────────┐                                                       │
│   │  RecordIDIterator │  Lightweight: fetches only record IDs               │
│   │  (sequential)     │                                                      │
│   └────────┬─────────┘                                                       │
│            │ yields IDs (str)                                                │
│            ▼                                                                 │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │                      ParallelFetcher (N workers)                      │  │
│   │                                                                        │  │
│   │   ┌──────────────────────────────────────────────────────────────┐   │  │
│   │   │                    ProcessorPipeline                          │   │  │
│   │   │                                                                │   │  │
│   │   │   ┌────────────────┐                                          │   │  │
│   │   │   │MetadataFetcher │  ID → fetch JSON-LD → parse → EcudoRecord│   │  │
│   │   │   └───────┬────────┘                                          │   │  │
│   │   │           │ EcudoRecord                                       │   │  │
│   │   │           ▼                                                    │   │  │
│   │   │   ┌────────────────┐                                          │   │  │
│   │   │   │  URLValidator  │  Validates all file URLs (optional)      │   │  │
│   │   │   └───────┬────────┘                                          │   │  │
│   │   │           │ EcudoRecord                                       │   │  │
│   │   │           ▼                                                    │   │  │
│   │   │   ┌────────────────┐                                          │   │  │
│   │   │   │DiversityFilter │  Limits similar datasets (optional)      │   │  │
│   │   │   └───────┬────────┘                                          │   │  │
│   │   │           │ EcudoRecord                                       │   │  │
│   │   │           ▼                                                    │   │  │
│   │   │   ┌────────────────┐                                          │   │  │
│   │   │   │RawRecordWriter │  Saves _raw JSON to JSONL (pass-through) │   │  │
│   │   │   └───────┬────────┘                                          │   │  │
│   │   │           │ EcudoRecord                                       │   │  │
│   │   │           ▼                                                    │   │  │
│   │   │   ┌────────────────┐                                          │   │  │
│   │   │   │OnedataConverter│  EcudoRecord → OnedataDataset + XML      │   │  │
│   │   │   └───────┬────────┘                                          │   │  │
│   │   │           │ OnedataDataset                                    │   │  │
│   │   │           ▼                                                    │   │  │
│   │   │   ┌────────────────┐                                          │   │  │
│   │   │   │  JSONLWriter   │  Saves final output                      │   │  │
│   │   │   └────────────────┘                                          │   │  │
│   │   │                                                                │   │  │
│   │   └──────────────────────────────────────────────────────────────┘   │  │
│   │                                                                        │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Key Components

### EcudoClient (`crawler/client.py`)

Low-level HTTP client for eCUDO API. Handles:
- Session management (async context manager)
- Retries with exponential backoff
- JSON fetching
- URL validation (HEAD requests)

```python
async with EcudoClient() as client:
    orgs = await client.get_organizations()
    metadata = await client.get_record_metadata(record_id)
```

### RecordIDIterator (`crawler/iterator.py`)

Async iterator that yields record IDs from an organization. Lightweight - fetches
only IDs (small payloads), not full metadata. This allows the heavy metadata
fetching to be parallelized by workers.

```python
async with EcudoClient() as client:
    iterator = RecordIDIterator(client, "iopan", max_records=100)
    async for record_id in iterator:
        # record_id is fed to the pipeline
        pass
```

### EcudoRecord (`models/record.py`)

Structured representation of a dataset. eCUDO-specific for now, but designed
to be easily extended when other data sources are added.

```python
@dataclass
class EcudoRecord:
    identifier: str
    title: str
    description: str
    publisher: str
    issued: str
    language: str
    keywords: list[str]
    files: list[FileInfo]
    spatial: str | None
    temporal: str | None
    _raw: dict  # Original JSON-LD for debugging
```

### OnedataDataset (`models/onedata.py`)

Output structure ready for Onedata registration:

```python
@dataclass
class OnedataDataset:
    name: str
    location: str
    pid: str
    metadata_xml: str
    files: list[OnedataFile]
```

### Processor[I, O] (`processors/base.py`)

Generic typed processor base class. Processors can:
- Transform data (`I` → `O`)
- Filter data (return `None` to skip)
- Have lifecycle methods (`open()`, `close()`)
- Report statistics (`get_stats()`)

```python
class MyProcessor(Processor[EcudoRecord, EcudoRecord]):
    async def process(self, record: EcudoRecord) -> EcudoRecord | None:
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
    MetadataFetcher(client, parser),
    URLValidator(client),
    DiversityFilter(max_similar=10),
    RawRecordWriter(raw_output),
    OnedataConverter(serializer),
    JSONLWriter(processed_output),
])

await pipeline.open()
result = await pipeline.process(record_id)  # Flows through all processors
await pipeline.close()

# Aggregate stats from all processors
stats = pipeline.get_stats()
```

### ParallelFetcher (`orchestration/parallel.py`)

Producer-consumer orchestrator for parallel processing:

```python
fetcher = ParallelFetcher(concurrency=128, queue_size=1000)
stats = await fetcher.run(
    id_source=record_id_iterator,
    pipeline=pipeline,
)
```

### Built-in Processors

| Processor | Input | Output | Description |
|-----------|-------|--------|-------------|
| `MetadataFetcher` | `str` (ID) | `EcudoRecord` | Fetches JSON-LD and parses |
| `URLValidator` | `EcudoRecord` | `EcudoRecord` | Validates file URLs |
| `DiversityFilter` | `EcudoRecord` | `EcudoRecord` | Limits similar titles |
| `RawRecordWriter` | `EcudoRecord` | `EcudoRecord` | Saves `_raw` to JSONL |
| `OnedataConverter` | `EcudoRecord` | `OnedataDataset` | Builds Onedata output |
| `JSONLWriter` | `T` | `T` | Writes to JSONL file |

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
from ecudo.models import EcudoRecord

class MyFilter(Processor[EcudoRecord, EcudoRecord]):
    def __init__(self, threshold: float):
        self.threshold = threshold
        self._filtered = 0
    
    async def process(self, record: EcudoRecord) -> EcudoRecord | None:
        if self.should_skip(record):
            self._filtered += 1
            return None
        return record
    
    def get_stats(self) -> dict:
        return {"filtered": self._filtered}
```

2. Add to pipeline in `cli.py`

### Adding a New Metadata Format

1. Create `serializers/myformat.py`:
```python
from ecudo.serializers.base import MetadataSerializer
from ecudo.models import EcudoRecord

class MyFormatSerializer(MetadataSerializer):
    @property
    def format_name(self) -> str:
        return "My Format"
    
    def serialize(self, record: EcudoRecord) -> str:
        return "..."
```

2. Add to `serializers/__init__.py`
3. Use in `OnedataConverter` (or create new converter)

### Adding a New Data Source

For a completely different API (not eCUDO):

1. Create new client in `crawler/`
2. Create parser that produces `EcudoRecord` (or new model)
3. Create `MetadataFetcher` variant for new API
4. Existing processors and serializers should work

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
