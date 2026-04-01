---
title: Processing Pipeline
topic: crawlers/arch/processing
generated: 2026-04-01
last_reviewed: 2026-04-01
source_modules:
  - crawlers/core/result.py
  - crawlers/core/processor.py
  - crawlers/core/sink.py
  - crawlers/core/workspace.py
  - crawlers/core/orchestration.py
  - crawlers/core/onedata.py
  - crawlers/processors/pipeline.py
  - crawlers/processors/fetchers.py
  - crawlers/processors/parsers.py
  - crawlers/processors/validators.py
  - crawlers/processors/converters.py
  - crawlers/processors/filters.py
  - crawlers/processors/tap.py
  - crawlers/sinks/jsonl.py
  - crawlers/sinks/null_sink.py
  - crawlers/default/workspace.py
source_commits:
  public-data-crawlers: d8a4e8e
status: draft
---

# Processing Pipeline

This document covers how datasets flow through the system — from raw
API items to Onedata-ready records written to disk. It describes the
core abstractions (`Result`, `Processor`, `Sink`), the pipeline that
chains them, the available processor implementations, workspace
management, and the parallel execution engine.

> For how the pipeline is constructed and driven by the plugin
> lifecycle, see [Plugin System](plugin-system.md). For a practical
> guide to customizing the pipeline, see
> [Writing Plugins](../guides/writing-plugins.md#custom-pipeline).

## Result Type

All processors and API calls use an explicit
[**Result**](glossary.md#result) type instead of exceptions or
`None` returns:

```python
type Result[T, E] = Ok[T] | Err[E]
```

`Ok[T]` and `Err[E]` are frozen, slotted dataclasses. Both provide a
`.map(fn)` method — `Ok` applies the function to the wrapped value,
`Err` returns itself unchanged. This enables safe chaining without
unwrapping.

The Result type makes success and failure paths explicit in function
signatures. A processor returning `Result[DatasetT, object]` tells
you at a glance that it may reject items, and the pipeline routes
each variant differently.

## Processor Abstraction

[**Processor**](glossary.md#processor) is the central building block.
It is a generic abstract class with three type parameters:

```python
class Processor[InT, OutT, StatsT: ProcessorStats](ABC):

    async def process(self, item: InT) -> Result[OutT, object]: ...
    async def open(self) -> None: ...
    async def close(self) -> None: ...
```

- **`InT`** — input type this processor accepts.
- **`OutT`** — output type on success.
- **`StatsT`** — statistics class (must extend `ProcessorStats`).

### Lifecycle

1. **`open()`** — initialize resources (files, connections). Called
   once before processing starts.
2. **`process(item)`** — transform a single item. Return `Ok(value)`
   to pass it forward, or `Err(reason)` to reject it.
3. **`close()`** — release resources. Called once after processing
   ends.

### Statistics

Every processor carries a `_stats` instance (created by
`_create_stats()`). The base `ProcessorStats` tracks three counters:
`processed`, `filtered`, `failed`. Subclasses extend this — for
example, `FetcherStats` adds `fetched` and `parsed` counters.

Processors are responsible for updating their own stats inside
`process()`. The pipeline collects stats from all processors via
`get_processor_stats()` for display.

### Enabled flag

Processors have an `enabled` flag. Disabled processors are skipped
entirely by the pipeline — no `open()`, `process()`, or `close()`
calls. This allows toggling stages via config (e.g.
`--no-url-validation`) without rebuilding the pipeline.

## ProcessorPipeline

[**ProcessorPipeline**](glossary.md#processorpipeline) chains
processors sequentially. It is itself a `Processor`, so it has the
same interface and can theoretically be nested (though this is not
used in practice).

The processing flow for a single item:

1. Feed the item to the first enabled processor.
2. On `Ok(value)` — pass `value` to the next enabled processor.
3. On `Err(reason)` — serialize `reason` via `errors.to_json()`,
   push to the **rejection sink**, and return the `Err` immediately.
   No further processors see the item.
4. If all processors return `Ok`, wrap the final value in `Ok` and
   return it.

The pipeline also provides:

- **`get_processor_info()`** — `(class_name, description, enabled)`
  tuples for display.
- **`get_processor_stats()`** — collects stats from enabled
  processors.
- **`get_artifacts()`** — collects output file paths from processors
  and the rejection sink.

## Available Processors

The framework ships six processor implementations in
`crawlers/processors/`. Plugins can use any combination and add
custom ones.

### DatasetFetcher

`Processor[str, DatasetT, FetcherStats]` — takes a dataset ID
(string), fetches full metadata via an async `fetch_fn`, then parses
it with a `Parser`. This two-step pattern is used when the API
returns IDs in listing calls and requires a separate request per
dataset (e.g. Ecudo).

### ParserProcessor

`Processor[RawT, DatasetT, ParserStats]` — wraps a `Parser`
protocol (any object with `parse(raw) -> dataset | None`). Used when
the API returns complete items directly (e.g. EODC STAC search), so
no additional fetching is needed.

### URLValidator

`Processor[DatasetT, DatasetT, URLValidatorStats]` — checks
accessibility of all file URLs in a dataset via HEAD requests. If
any URL fails, the entire dataset is rejected. Uses structural typing
via a `Dataset` protocol requiring `identifier` and `files`
attributes.

### DiversityFilter

`Processor[DatasetT, DatasetT, DiversityFilterStats]` — groups
datasets by title similarity using `difflib.SequenceMatcher`. Limits
each group to `max_similar` items (default 10) with a configurable
`similarity_threshold` (default 0.85). Useful for APIs that return
many near-duplicate entries.

### OnedataConverter

`Processor[DatasetT, OnedataDataset, ConverterStats]` — the final
transformation step. Calls the `MetadataBuilder` to produce XML,
then constructs an `OnedataDataset` with resolved file paths. When
multiple files share a filename, the converter progressively adds
URL path segments until all paths are unique. Always returns `Ok`
(never rejects).

### Tap

`Processor[T, T, TapStats]` — a pass-through that pushes a copy of
each item to a [**Sink**](glossary.md#sink), optionally applying a
`transform` function first. The original item is forwarded unchanged.
Tap does not manage sink lifecycle — that is `RunContext`'s
responsibility.

Taps are typically placed at observation points:
- Before conversion — to capture the raw parsed dataset.
- After conversion — to capture the final Onedata record.

## Sink Abstraction

[**Sink**](glossary.md#sink) is the output side of the pipeline — a
destination that accepts data.

```python
class Sink[T](ABC):
    async def open(self) -> None: ...
    async def push(self, item: T) -> None: ...
    async def close(self) -> None: ...
```

Two implementations are provided:

- **`JSONLSink`** — appends JSON objects as lines to a file. Opens in
  append mode (safe for resume) and flushes after each write (crash
  safety).
- **`NullSink`** — discards all items. Used when a sink is
  structurally required but the output is disabled (e.g. rejection
  tracking turned off).

## Workspace and Run Management

Each crawl execution produces a **run directory** with a fixed
structure:

```
<workspace>/runs/<timestamp>_<plugin>_<context>/
  config.json       # Config snapshot at run start
  state.json        # Status, timestamps, running stats
  raw.jsonl         # Raw parsed datasets (via Tap)
  processed.jsonl   # Final OnedataDataset records (via Tap)
  rejected.jsonl    # Rejected items with reasons
```

[**RunContext**](glossary.md#runcontext) manages this directory's
lifecycle:

1. **`open(config_snapshot)`** — creates the directory, writes
   `config.json`, initializes `state.json` with status `"running"`,
   and calls `open_sinks()`.
2. **`save_stats(stats)`** — periodically updates `state.json` with
   current statistics (called by the orchestrator).
3. **`close(status)`** — calls `close_sinks()` and writes final
   `state.json` with status `"completed"`, `"interrupted"`, or
   `"failed"`.

**`DefaultRunContext`** is the standard implementation. It creates
three sinks — `raw_sink`, `processed_sink`, and `rejection_sink`
(the latter is a `NullSink` when rejection tracking is disabled).

## Parallel Execution

`run_parallel_pipeline()` drives the pipeline with concurrent
workers using a producer–consumer pattern:

<!-- DIAGRAM
What to show: The producer-consumer architecture — one producer task
  reading from the async iterator into a bounded queue, N worker
  tasks consuming from the queue and calling pipeline.process(), with
  Ok/Err routing and periodic state callbacks.
Context: This is in the "Parallel Execution" section, after the
  workspace description. It is the main runtime diagram.
Key participants: source_iterator, producer task, asyncio.Queue,
  N worker tasks, pipeline.process(), state_callback
Related visuals in this doc: none yet
-->

1. A **producer** task reads from the source iterator (API client's
   `iterate_datasets()`) and puts items into a bounded
   `asyncio.Queue`.
2. **N worker** tasks (configurable via `concurrency`, default 128)
   consume from the queue and call `pipeline.process(item)`.
3. Workers classify results: `Ok` increments `processed`, `Err`
   increments `filtered`, exceptions increment `failed`.
4. Every `state_save_interval` items (default 100), the
   `state_callback` is invoked to persist stats to `state.json`.
5. The producer sends `None` sentinels (one per worker) to signal
   completion.
6. A Rich progress bar shows live throughput.

The queue bounds memory usage — the producer blocks when the queue
is full (`queue_size`, default 1000), creating natural backpressure
against the API.

## Typical Pipeline Compositions

Two patterns are used by the built-in plugins:

**Ecudo** (custom pipeline — API returns IDs, needs separate fetch):
```
DatasetFetcher → URLValidator → DiversityFilter → Tap(raw) → OnedataConverter → Tap(processed)
```
Input: `str` (dataset ID). The fetcher calls the API and parses
JSON-LD.

**EODC** (default pipeline — API returns complete items):
```
ParserProcessor → URLValidator → Tap(raw) → OnedataConverter → Tap(processed)
```
Input: `dict` (raw STAC item from POST /search).

Both pipelines use a rejection sink that captures `Err` values as
JSONL for post-mortem analysis.

## Related Documentation

- **[Architecture Overview](_overview.md)** — system layers and data
  flow
- **[Plugin System](plugin-system.md)** — how plugins build and
  drive pipelines
- **[Metadata](metadata.md)** — the MetadataBuilder used by
  OnedataConverter
- **[Writing Plugins](../guides/writing-plugins.md)** — customizing
  the pipeline
- **[Glossary](glossary.md)** — quick definitions
