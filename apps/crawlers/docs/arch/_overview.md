---
title: Crawlers Architecture Overview
description: >
  High-level architecture of the crawlers framework — a system for
  harvesting scientific dataset metadata from external APIs and
  producing Onedata-compatible registration records. Covers the
  two-layer design, data flow, and key design decisions.
audience: internal-developer-onboarding
source_modules:
  - apps/crawlers/src/crawlers/core/config.py
  - apps/crawlers/src/crawlers/core/dataset.py
  - apps/crawlers/src/crawlers/core/http.py
  - apps/crawlers/src/crawlers/core/jsonl.py
  - apps/crawlers/src/crawlers/core/plugin.py
  - apps/crawlers/src/crawlers/core/result.py
  - apps/crawlers/src/crawlers/core/runner.py
  - apps/crawlers/src/crawlers/core/workspace.py
  - apps/crawlers/src/crawlers/metadata/datacite.py
  - apps/crawlers/src/crawlers/metadata/openaire.py
  - packages/onedata-dataset/src/onedata_dataset/
source_commits:
  public-data-crawlers: 3c68b70
---

# Crawlers Architecture Overview

The `crawlers` package is a framework for harvesting scientific
dataset metadata from external APIs and producing Onedata-compatible
registration records — structured entries that Onedata uses to make
datasets discoverable and accessible within spaces. Adding support
for a new data source requires only the source-specific parts — API
client, parser, config — while the framework handles parallel
execution, workspace management, CLI generation, and metadata
serialization.

```mermaid
graph TB
    subgraph Plugins["🔌 Plugins · crawlers/plugins/"]
        P["Source-specific logic\nAPI client, parser, config, plugin class"]
    end

    subgraph Core["🏗️ Core · crawlers/core/"]
        C["Framework primitives\nCrawlerPlugin, HttpClient, Result,\nrunner, workspace"]
    end

    subgraph Packages["📦 Packages"]
        CF["⚙️ confline\nconfig framework"]
        DS["📦 onedata-dataset\nOnedataDataset, OnedataFile"]
    end

    subgraph Meta["🏷️ Metadata · crawlers/metadata/"]
        M["XML record types\nDataCiteRecord, OpenAIRERecord"]
    end

    Plugins -->|extends| Core
    Core -->|uses| Packages
    Plugins -->|uses| Meta

    classDef plugin fill:#FFE4B5,stroke:#E8890C,color:#000
    classDef core fill:#E6E6FA,stroke:#5B4B8A,color:#000
    classDef meta fill:#A8DADC,stroke:#1864AB,color:#000
    classDef pkg fill:#95D5B2,stroke:#2D6A4F,color:#000

    class P plugin
    class C core
    class CF,DS pkg
    class M meta
```

## Why This Architecture

The design separates concerns by rate of change:

- **Core** (`apps/crawlers/src/crawlers/core/`) defines the stable
  vocabulary — the [plugin base class](plugin-system.md#crawlerplugin),
  HTTP client, Result type, and workspace runtime. 
  These contracts rarely change.

- **Metadata** (`apps/crawlers/src/crawlers/metadata/`) provides
  [DataCiteRecord and OpenAIRERecord](metadata.md) — structured
  records that produce standards-compliant XML via `to_xml()`.
  These evolve independently of plugins when metadata standards
  change.

- **Plugins** (`apps/crawlers/src/crawlers/plugins/`) contain only the
  source-specific logic: an API client facade, a parser, a config,
  and a plugin class that wires them together.

This means adding a new crawler (like Bgee or VIP) doesn't touch
the runner, the config system, or the metadata builders — you
implement `iterate_datasets()` and `process()` and the framework
does the rest. See the [Glossary](glossary.md) for concise
definitions.

## Data Flow

A crawl execution follows a fixed pattern regardless of the
plugin. The plugin's `iterate_datasets()` yields raw items from
the external API, N concurrent workers call `process()` on each
item, and results are routed to JSONL sinks in the
[run directory](plugin-system.md#workspace-and-run-management).
See [Parallel Execution](plugin-system.md#parallel-execution) for
the full mechanics.

```mermaid
graph LR
    API["🌐 External API"]
    ITER["⚙️ iterate_datasets"]
    Q["📬 asyncio.Queue"]

    subgraph Workers["⚙️ N Workers · concurrent"]
        PROC["🔄 process·item·\nfetch → parse → build"]
    end

    subgraph RunDir["📁 run directory"]
        direction TB
        processed["📄 processed.jsonl"]
        rejected["📄 rejected.jsonl"]
        st["📄 state.json"]
    end

    API --> ITER --> Q --> Workers

    PROC -->|"Ok(dataset)"| processed
    PROC -->|"Err(failure)"| rejected
    PROC -->|None| skip["⏭️ skip"]
    Workers -.->|stats| st

    classDef external fill:#A8DADC,stroke:#1864AB,color:#000
    classDef internal fill:#4ECDC4,stroke:#0B7285,color:#000
    classDef data fill:#E6E6FA,stroke:#5B4B8A,color:#000
    classDef error fill:#E63946,stroke:#9D0208,color:#fff
    classDef skip fill:#FFD700,stroke:#F08C00,color:#000

    class API external
    class ITER,PROC internal
    class Q internal
    class processed,st data
    class rejected error
    class skip skip
```

## Key Design Decisions

**Explicit error handling with Result** — the framework uses
`Ok[T] | Err[E]` instead of exceptions for expected failures.
This makes success/failure boundaries visible in type signatures
and lets the runner route rejected items to a dedicated sink for
post-mortem analysis.

**Direct plugin contract** — plugins implement `iterate_datasets()`
and `process()` directly on the plugin class, with no intermediate
abstractions like pipeline stages or spec objects. Two methods,
full control over per-item logic.

## What's Next

| Goal | Start with |
|------|------------|
| Understand plugin structure and crawl lifecycle | [Plugin System](plugin-system.md) |
| Understand how XML metadata is produced | [Metadata](metadata.md) |
| Build a new crawler plugin | [Writing Plugins](../guides/writing-plugins.md) |
| Look up a term | [Glossary](glossary.md) |
