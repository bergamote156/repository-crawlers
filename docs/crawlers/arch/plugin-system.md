---
title: Plugin System
topic: crawlers/arch/plugin-system
generated: 2026-04-01
last_reviewed: 2026-04-01
source_modules:
  - crawlers/core/plugin.py
  - crawlers/core/api.py
  - crawlers/default/plugin.py
  - crawlers/default/config.py
  - crawlers/default/workspace.py
  - crawlers/cli.py
  - crawlers/plugins/__init__.py
source_commits:
  public-data-crawlers: d8a4e8e
status: draft
---

# Plugin System

The plugin system defines how crawlers are structured, discovered,
and executed. It has two layers: a minimal `CrawlerPlugin` base that
handles command registration, config loading, and CLI dispatch; and
a batteries-included `DefaultCrawlerPlugin` that adds a complete
crawl lifecycle on top.

> For the config machinery that powers argument parsing and
> multi-source resolution, see [Configuration](configuration.md).
> For a step-by-step guide to creating plugins, see
> [Writing Plugins](../guides/writing-plugins.md).

## CrawlerPlugin

[**CrawlerPlugin**](glossary.md#crawlerplugin) is the abstract base
for all plugins. It provides three things: command collection, CLI
argument generation, and config-aware dispatch.

### Command Registration

Commands are declared with the `@command()` decorator on async
methods:

```python
@command("list-orgs", EcudoApiConfig, help="List available organizations")
async def list_organizations(self, config: EcudoApiConfig) -> None:
    ...
```

The decorator attaches a `CommandDef` (name, help text, method name,
config class) to the method. When a subclass is created,
`__init_subclass__` scans all methods for `_command_def` attributes
and collects them into the class-level `_commands` dict.

This means commands are inherited — a method decorated in a parent
class is available in all subclasses unless overridden.

### CLI Argument Generation

`register_args(parser)` builds argparse structure from the collected
commands:

1. Adds a global `-c / --config` option for the YAML config file.
2. Creates a subparser per command.
3. For each command's config class, iterates `ConfigSchema` groups
   and adds argparse arguments (with groups matching the config
   class hierarchy for organized `--help` output).

### Dispatch

`run(cli_args)` reads the selected command from the parsed namespace,
calls `load_config()` to build the config object from all sources
(see [Configuration — Resolution Priority](configuration.md#resolution-priority)),
and invokes the decorated method with the config.

## DefaultCrawlerPlugin

[**DefaultCrawlerPlugin**](glossary.md#defaultcrawlerplugin) extends
`CrawlerPlugin` with everything needed for a typical crawl: client
management, pipeline construction, parallel execution, workspace
persistence, and Rich display.

### Auto-registered crawl command

When a concrete subclass sets `name` as a string class attribute,
`__init_subclass__` automatically registers a `"crawl"` command
pointing to `run_crawl()` with the class's `config_class`. You do
not need to decorate `run_crawl` yourself — just set `name` and
`config_class`.

### DefaultCrawlSpec

[**DefaultCrawlSpec**](glossary.md#defaultcrawlspec) is the
dataclass returned by `prepare_crawl()`. It describes *what* to run
without dictating *how*:

- **`client`** — `ApiClient` instance (session opened by the
  framework).
- **`iterator_opts`** — options passed to
  `client.iterate_datasets()`.
- **`parser`** — `Parser` that transforms raw API items to dataset
  models.
- **`metadata_builder`** — `MetadataBuilder` that produces XML per
  dataset.
- **`run_context_name`** — identifier used in the run directory name
  (default: `"default"`).
- **`banner_subtitle`** — shown in the startup banner (optional).

### Crawl Lifecycle

`run_crawl(config)` orchestrates the full crawl in a fixed sequence:

<!-- DIAGRAM
What to show: The crawl lifecycle as a vertical sequence — numbered
  steps from prepare_crawl through ctx.open, client session,
  before_crawl, build_pipeline, run_parallel_pipeline, after_crawl,
  to ctx.close. Show the try/except structure with interrupted/failed
  branches leading to ctx.close with appropriate status.
Context: This is the central lifecycle diagram for the plugin system
  doc. It should show the happy path and error handling.
Key participants: prepare_crawl, RunContext, ApiClient (async with),
  before_crawl, build_pipeline, run_parallel_pipeline, after_crawl,
  ctx.close
Related visuals in this doc: none yet
-->

1. **`prepare_crawl(config)`** — plugin returns a
   `DefaultCrawlSpec`.
2. **`_create_run_context()`** — creates a `DefaultRunContext` with
   a timestamped run directory.
3. **`ctx.open()`** — creates the directory, writes `config.json`,
   opens sinks.
4. **`async with spec.client`** — opens the HTTP session.
5. **`before_crawl(spec)`** — plugin hook for validation (e.g.
   check that a requested organization exists).
6. **`build_pipeline(config, spec, ctx)`** — constructs the
   `ProcessorPipeline`.
7. **`pipeline.open()`** — initializes all enabled processors.
8. **`run_parallel_pipeline(...)`** — parallel execution with
   progress tracking.
9. **`pipeline.close()`** — always called (in a `finally` block).
10. **`after_crawl()`** — plugin hook for post-crawl actions.
11. **`ctx.close(status)`** — closes sinks, writes final state.

On `KeyboardInterrupt` or `CancelledError`, status is set to
`"interrupted"`. On other exceptions, status is `"failed"` and the
exception re-raises after cleanup.

### Default Pipeline

If a plugin does not override `build_pipeline()`, it gets:

```
ParserProcessor → URLValidator → Tap(raw) → OnedataConverter → Tap(processed)
```

With the rejection sink wired to the pipeline. See
[Processing — Typical Pipeline Compositions](processing.md#typical-pipeline-compositions)
for how plugins customize this.

### Display

`DefaultCrawlerPlugin` uses Rich to print:
- **Banner** — plugin class name, subtitle, run directory.
- **Pipeline tree** — numbered list of processors with
  enabled/disabled indicators.
- **Summary** — per-processor stats table, overall counts, output
  file paths, run directory, and next steps.

## API Client

[**ApiClient**](glossary.md#apiclient) is the generic async HTTP
client base. It is closely tied to the plugin system — each plugin
implements a subclass, and `DefaultCrawlerPlugin` manages its
session lifecycle.

```python
class ApiClient[OptsT, DatasetT](ABC):
    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, ...): ...
    def iterate_datasets(self, opts: OptsT) -> AsyncIterator[DatasetT]: ...
```

### Generic parameters

- **`OptsT`** — iterator options type. For example,
  `EcudoIteratorOpts` carries `org_id`, `page_size`, `max_datasets`.
- **`DatasetT`** — type yielded by the iterator. Ecudo yields `str`
  (dataset IDs requiring a second fetch), EODC yields `dict` (full
  STAC items).

### HTTP handling

The base class provides:

- **`get_json(url)`** / **`post_json(url, body)`** — convenience
  methods returning `Result[dict, ApiFailure]`.
- **`validate_url(url)`** — HEAD request returning
  `Result[bool, ApiFailure]`. Used by `URLValidator`.
- **`_request_json(method, url)`** — core method with retry loop.
  On network/timeout errors, retries with exponential backoff
  (`2^attempt` seconds). Returns `Err(HttpFailure)` on non-200
  responses or `Err(TimeoutFailure)` when all retries are exhausted.

### Session management

The client uses `aiohttp.ClientSession` via async context manager.
`DefaultCrawlerPlugin.run_crawl()` opens it with `async with
spec.client:` — the session lives for the entire crawl duration.
Attempting to use the client outside the context manager raises
`RuntimeError`.

## Plugin Registry

Plugins are registered in `crawlers/plugins/__init__.py` as a
hardcoded list:

```python
REGISTERED_PLUGINS = [EcudoPlugin(), EODCPlugin()]
```

The CLI entry point (`crawlers/cli.py`) iterates this list, creates
an argparse subparser per plugin (using `plugin.name`), and calls
`plugin.register_args()`. At runtime, the selected plugin's `run()`
method is invoked.

## Related Documentation

- **[Architecture Overview](_overview.md)** — system layers and data
  flow
- **[Configuration](configuration.md)** — config system that powers
  argument parsing
- **[Processing](processing.md)** — pipeline and processor
  abstractions
- **[Metadata](metadata.md)** — MetadataBuilder used in
  DefaultCrawlSpec
- **[Writing Plugins](../guides/writing-plugins.md)** — practical
  plugin creation guide
- **[Glossary](glossary.md)** — quick definitions
