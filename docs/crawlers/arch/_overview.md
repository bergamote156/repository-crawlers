---
title: Crawlers Architecture Overview
topic: crawlers/arch
generated: 2026-04-01
last_reviewed: 2026-04-01
source_modules:
  - crawlers/core/config.py
  - crawlers/core/plugin.py
  - crawlers/core/api.py
  - crawlers/core/processor.py
  - crawlers/core/result.py
  - crawlers/core/sink.py
  - crawlers/core/workspace.py
  - crawlers/core/orchestration.py
  - crawlers/default/plugin.py
  - crawlers/processors/pipeline.py
  - crawlers/metadata/datacite.py
  - crawlers/metadata/openaire.py
source_commits:
  public-data-crawlers: d8a4e8e
status: draft
---

# Crawlers Architecture Overview

The `crawlers` package is a framework for harvesting scientific
dataset metadata from external APIs and producing Onedata-compatible
registration records. Each record contains a dataset name, a
location path, a persistent identifier, standards-compliant XML
metadata (OpenAIRE or DataCite), and a file manifest.

The framework is designed so that adding support for a new data
source requires only the source-specific parts — API client, parser,
config — while pipeline construction, parallel execution, workspace
management, and CLI generation are handled by the framework.

## Architecture Layers

The system is organized in four layers, from foundation to concrete:

<!-- DIAGRAM
What to show: Four horizontal layers stacked bottom-to-top:
  1. Core (bottom) — abstractions: ConfigBase, CrawlerPlugin,
     Processor, Sink, Result, ApiClient, RunContext, MetadataBuilder
  2. Components — reusable implementations: ProcessorPipeline,
     DatasetFetcher, ParserProcessor, URLValidator, OnedataConverter,
     DiversityFilter, Tap, JSONLSink, DataCiteBuilder, OpenAIREBuilder
  3. Default Template — batteries-included: DefaultCrawlerPlugin,
     DefaultCrawlConfig, DefaultRunContext, DefaultCrawlSpec
  4. Plugins (top) — concrete: EcudoPlugin, EODCPlugin
  Show arrows indicating "extends/uses" relationships between layers.
Context: This is the primary architecture diagram, placed right after
  introducing the layered design.
Key participants: all four layers with their main classes
Related visuals in this doc: data flow diagram below
-->

### Core (`crawlers/core/`)

Abstract base classes and framework primitives. Nothing here is
specific to any data source or output format:

- **[ConfigBase](configuration.md)** — declarative config with
  auto-generated CLI, YAML, and ENV support.
- **[CrawlerPlugin](plugin-system.md#crawlerplugin)** — command
  registration, config loading, CLI dispatch.
- **[Processor](processing.md#processor-abstraction)** — generic
  typed pipeline stage with statistics.
- **[Sink](processing.md#sink-abstraction)** — output destination.
- **[Result](processing.md#result-type)** — `Ok[T] | Err[E]` for
  explicit error handling.
- **[ApiClient](plugin-system.md#api-client)** — async HTTP client
  with retries.
- **[RunContext](processing.md#workspace-and-run-management)** — run
  directory and state persistence.
- **[MetadataBuilder](metadata.md)** — abstract XML generator.

### Components (`crawlers/processors/`, `crawlers/sinks/`, `crawlers/metadata/`)

Reusable, concrete implementations of the core abstractions:

- **[ProcessorPipeline](processing.md#processorpipeline)** — chains
  processors with `Ok`/`Err` routing.
- **Processors** — `DatasetFetcher`, `ParserProcessor`,
  `URLValidator`, `OnedataConverter`, `DiversityFilter`, `Tap`.
- **Sinks** — `JSONLSink` (append-mode JSONL), `NullSink`.
- **Metadata builders** — `DataCiteBuilder` (Kernel 4.5),
  `OpenAIREBuilder` (v4.0).

### Default Template (`crawlers/default/`)

Batteries-included base that composes core and components into a
complete crawl lifecycle:

- **[DefaultCrawlerPlugin](plugin-system.md#defaultcrawlerplugin)**
  — auto-registered `crawl` command, client management, pipeline
  construction, parallel execution, Rich display.
- **[DefaultCrawlConfig](configuration.md#config-inheritance)** —
  standard config groups (API, output, processing).
- **[DefaultRunContext](processing.md#workspace-and-run-management)**
  — three JSONL sinks (raw, processed, rejected).

### Plugins (`crawlers/plugins/`)

Concrete crawlers for specific data sources. Each plugin provides:
an API client, a parser, a config, and a plugin class. Currently:

- **Ecudo** — eCUDO.pl science repositories (JSON-LD API, OpenAIRE
  metadata).
- **EODC** — EODC STAC API (Sentinel-1 collections, DataCite
  metadata).

## Data Flow

A crawl execution follows a fixed pattern regardless of the plugin:

<!-- DIAGRAM
What to show: Horizontal data flow from left to right:
  API → iterate_datasets() → [Queue] → Pipeline stages → Sinks
  Show the pipeline expanding into its processor chain:
  Parse → Validate → (Filter) → Tap(raw) → Convert → Tap(processed)
  With Err values branching down to rejection sink.
  On the right, show the run directory with output files.
Context: Second diagram in the overview, after the layers diagram.
  Shows the runtime data flow, not the static architecture.
Key participants: ApiClient, asyncio.Queue, processors, sinks,
  run directory
Related visuals in this doc: layers diagram above
-->

1. **Listing** — The API client's `iterate_datasets()` yields items
   (IDs or full records) from the external API with pagination.
2. **Queuing** — A producer task puts items into a bounded
   `asyncio.Queue`. Backpressure prevents unbounded memory growth.
3. **Processing** — N concurrent workers pull items from the queue
   and feed them through the processor pipeline. Each processor
   returns `Ok(value)` to pass the item forward or `Err(reason)` to
   reject it.
4. **Observation** — `Tap` processors push copies of items to sinks
   at key pipeline stages (raw parsed data, final converted data).
5. **Conversion** — `OnedataConverter` calls the metadata builder to
   produce XML and resolves file path collisions.
6. **Output** — `JSONLSink` writes records as append-mode JSONL
   files. The run directory contains `raw.jsonl`, `processed.jsonl`,
   and `rejected.jsonl`.
7. **State** — `RunContext` periodically persists crawl statistics
   to `state.json` for monitoring and potential resume.

## Key Design Decisions

### Explicit error handling with Result

The framework uses `Ok[T] | Err[E]` instead of exceptions for
expected failures (HTTP errors, parse failures, validation
rejections). This makes the success/failure boundary visible in type
signatures and allows the pipeline to route rejected items to a
dedicated sink for post-mortem analysis.

Unexpected failures (bugs, infrastructure issues) still raise
exceptions and are caught at the orchestration level.

### Generic typed processors

`Processor[InT, OutT, StatsT]` uses three generic parameters to
enforce type safety across the pipeline. While Python's type system
does not enforce this at runtime, it provides IDE support and
documents the data flow clearly.

### Declarative configuration

Config fields declare *all* their sources (CLI, YAML, ENV) in one
place via `opt()`. The framework resolves values at runtime with a
fixed priority: CLI > command YAML > plugin YAML > global YAML >
ENV > defaults. This eliminates scattered argument parsing and
ensures consistent behavior regardless of how a value is provided.

### Plugin as composition, not inheritance

`DefaultCrawlerPlugin` provides the lifecycle, but plugins describe
*what* to run via `DefaultCrawlSpec` rather than *how* to run it.
The spec is a simple data object — client, parser, metadata builder,
options. The framework consumes this spec to drive execution. Plugins
that need more control can override `build_pipeline()` or lifecycle
hooks.

## Next Steps

**Understanding the architecture:**
- [Configuration](configuration.md) — config system deep-dive
- [Processing](processing.md) — pipeline, processors, sinks,
  orchestration
- [Plugin System](plugin-system.md) — plugin framework and API
  client
- [Metadata](metadata.md) — DataCite and OpenAIRE builders
- [Glossary](glossary.md) — terms and definitions

**Building a plugin:**
- [Writing Plugins](../guides/writing-plugins.md) — step-by-step
  guide with examples from Ecudo and EODC
