---
title: Glossary
topic: crawlers/arch
generated: 2026-04-01
last_reviewed: 2026-04-01
source_modules:
  - crawlers/core/config.py
  - crawlers/core/plugin.py
  - crawlers/core/processor.py
  - crawlers/core/result.py
  - crawlers/core/sink.py
  - crawlers/core/workspace.py
  - crawlers/core/orchestration.py
  - crawlers/core/api.py
  - crawlers/core/metadata.py
  - crawlers/processors/pipeline.py
  - crawlers/default/plugin.py
source_commits:
  public-data-crawlers: d8a4e8e
status: draft
---

# Glossary

Quick-reference definitions for concepts used throughout the crawlers
architecture documentation. Each entry links to the detail doc where
the concept is explained in full.

---

## ApiClient

Generic async HTTP client base class (`ApiClient[OptsT, DatasetT]`)
that provides session management, retries with exponential backoff,
and typed error handling via `Result`. Every plugin implements a
concrete subclass that knows how to iterate datasets from its API.
Learn more: [Plugin System](plugin-system.md#api-client).

## Command

A named CLI entry point registered on a plugin via the `@command()`
decorator. Each command is bound to a `ConfigBase` subclass that
defines its arguments. The framework auto-generates argparse from the
config schema and dispatches to the decorated method.
Learn more: [Plugin System](plugin-system.md#command-registration).

## ConfigBase

Base class for declarative configuration. Subclasses are dataclasses
whose fields carry CLI, environment variable, and YAML metadata via
`opt()`. The framework auto-builds a `ConfigSchema` and resolves
values from multiple sources at runtime.
Learn more: [Configuration](configuration.md#configbase-and-opt).

## CrawlerPlugin

Abstract base class for all plugins. Collects `@command()`-decorated
methods via `__init_subclass__`, builds argparse, loads config from
multiple sources, and dispatches to the selected command.
Learn more: [Plugin System](plugin-system.md#crawlerplugin).

## DefaultCrawlerPlugin

Batteries-included base class that extends `CrawlerPlugin` with a
complete crawl lifecycle: config loading, client session management,
pipeline construction, parallel execution, state persistence, and
Rich-based display. Plugins subclass this and implement
`prepare_crawl()`.
Learn more: [Plugin System](plugin-system.md#defaultcrawlerplugin).

## DefaultCrawlSpec

Dataclass returned by `prepare_crawl()`. Describes everything needed
for a crawl run: the API client, iterator options, parser, and
metadata builder. The framework consumes the spec — the plugin only
describes *what* to run.
Learn more: [Plugin System](plugin-system.md#defaultcrawlspec).

## MetadataBuilder

Abstract base (`MetadataBuilder[DatasetT]`) with a single method
`build(dataset) -> str` that produces metadata XML (DataCite or
OpenAIRE) from a parsed dataset. Concrete builders use a template
method pattern with overridable section builders.
Learn more: [Metadata](metadata.md).

## Processor

Generic abstract base (`Processor[InT, OutT, StatsT]`) for pipeline
stages that transform data. Processors have a lifecycle
(`open`/`close`), return `Result` values, track statistics, and can
be enabled or disabled.
Learn more: [Processing](processing.md#processor-abstraction).

## ProcessorPipeline

A `Processor` subclass that chains multiple processors sequentially.
`Ok` values flow forward; `Err` values short-circuit to the rejection
sink. The pipeline delegates lifecycle and stats to its children.
Learn more: [Processing](processing.md#processorpipeline).

## Result

Explicit error-handling type inspired by Rust/Erlang:
`type Result[T, E] = Ok[T] | Err[E]`. Used throughout the pipeline
and API client to make success and failure paths visible in types.
Learn more: [Processing](processing.md#result-type).

## RunContext

Abstract base that manages a single crawl run's directory, config
snapshot, state persistence, and sink lifecycle. `DefaultRunContext`
provides the standard implementation with three JSONL sinks.
Learn more: [Processing](processing.md#workspace-and-run-management).

## Sink

Abstract base (`Sink[T]`) for output destinations that accept
pipeline data. Lifecycle (`open`/`push`/`close`) is managed by
`RunContext`, not by the sink itself.
Learn more: [Processing](processing.md#sink-abstraction).

## Tap

A pass-through processor that pushes a copy of each item to a `Sink`
(optionally transformed) while forwarding the original unchanged.
Used to observe intermediate pipeline states (e.g. raw parsed data
before conversion).
Learn more: [Processing](processing.md#available-processors).

---

## Related Documentation

- **[Architecture Overview](_overview.md)** — high-level system design
- **[Configuration](configuration.md)** — config system deep-dive
- **[Processing](processing.md)** — pipeline, processors, sinks,
  orchestration
- **[Plugin System](plugin-system.md)** — plugin framework and API
  client
- **[Metadata](metadata.md)** — DataCite and OpenAIRE builders
- **[Writing Plugins](../guides/writing-plugins.md)** — step-by-step
  plugin guide
