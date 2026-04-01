---
title: Configuration System
topic: crawlers/arch/configuration
generated: 2026-04-01
last_reviewed: 2026-04-01
source_modules:
  - crawlers/core/config.py
  - crawlers/core/plugin.py
  - crawlers/default/config.py
  - crawlers/plugins/ecudo/config.py
  - crawlers/plugins/eodc/config.py
source_commits:
  public-data-crawlers: d8a4e8e
status: draft
---

# Configuration System

The configuration system lets you declare config fields once — as
annotated dataclass fields — and get CLI argument parsing, YAML file
loading, environment variable support, and help text generation for
free. Values from all sources merge at runtime according to a fixed
priority order.

> This document covers the config machinery itself. For how configs
> integrate with the plugin lifecycle, see
> [Plugin System](plugin-system.md). For practical examples of writing
> plugin configs, see [Writing Plugins](../guides/writing-plugins.md).

## Key Concepts

- **[`ConfigBase`](#configbase-and-opt)** — base class that turns
  any subclass into a dataclass with an auto-built schema.
- **[`opt()`](#configbase-and-opt)** — field wrapper that attaches
  CLI/ENV/YAML metadata to a dataclass field.
- **[`ConfigSchema`](#schema-internals)** — pre-computed schema
  with field groups, types, and CLI info. Built once per class at
  import time.
- **[Resolution priority](#resolution-priority)** — the fixed order
  in which sources override each other.

## ConfigBase and opt()

Every config class inherits from `ConfigBase`. The base class
intercepts subclass creation via `__init_subclass__`: it applies
`@dataclass` and builds a `ConfigSchema` automatically. You never
call `@dataclass` yourself.

Fields use `opt()` instead of `dataclasses.field()` to attach
metadata describing how each value can be provided:

```python
class ApiConfig(ConfigBase):
    """Base configuration for API connections."""

    base_url: str = opt(..., description="API base URL")
    timeout: int = opt(15, description="Request timeout in seconds")
    max_retries: int = opt(3, description="Maximum retry attempts")
```

### opt() parameters

| Parameter | Type | Default | Effect |
|-----------|------|---------|--------|
| `default` | any | `...` (required) | Default value. `...` means the field is required. |
| `cli` | `str \| tuple \| False \| None` | `None` | CLI flag name(s). `None` auto-generates from field name (`my_field` becomes `--my-field`). `False` disables CLI. |
| `env` | `str \| False \| None` | `None` | ENV var suffix. `None` auto-generates (`my_field` becomes `CRAWLER_MY_FIELD`). `False` disables ENV. |
| `yaml_key` | `str \| False \| None` | `None` | YAML key. `None` uses the field name. `False` disables YAML loading. |
| `description` | `str` | `""` | Help text for CLI `--help` and documentation. |

### Field type handling

The schema builder inspects field type annotations:

- **`bool`** — CLI generates `action="store_true"` (flag without
  value).
- **`int`, `float`, `str`** — CLI passes the corresponding
  `type=` to argparse for automatic coercion.
- **`Optional[X]`** / **`X | None`** — unwrapped to `X` for type
  handling; the field is not treated as required.
- **Nested dataclass** — the field gets a recursive `ConfigSchema`.
  Nested configs are YAML-only (no CLI generation). See
  [Nested Configs](#nested-configs).

### Positional arguments

To create a positional CLI argument (like `organization` in Ecudo),
set `cli` to a bare name without dashes:

```python
organization: str = opt(
    ...,
    cli="organization",
    description="Organization ID (e.g. iopan)",
)
```

The framework detects that the name does not start with `-` and
registers it as a positional argument.

## Resolution Priority

When multiple sources provide a value for the same field, the
highest-priority source wins. The order, from highest to lowest:

1. **CLI arguments** — `--base-url https://...`
2. **Command YAML** —
   `plugins.<plugin>.commands.<command>.<key>`
3. **Plugin YAML** — `plugins.<plugin>.<key>`
4. **Global YAML** — `global.<key>`
5. **Environment variables** — `CRAWLER_<SUFFIX>`
6. **Default values** — from the `opt()` call

### How YAML lookup works

Given a config file loaded via `-c config.yaml`, the framework reads
three sections and checks each field's `yaml_key` against them in
order:

```yaml
global:
  timeout: 30
  output_dir: ./output

plugins:
  ecudo:
    base_url: http://custom.ecudo.pl
    timeout: 60

    commands:
      crawl:
        page_size: 50
        max_records: 1000
```

For the `timeout` field when running `crawlers ecudo crawl`:
1. Command YAML (`plugins.ecudo.commands.crawl.timeout`) — not set.
2. Plugin YAML (`plugins.ecudo.timeout`) — **60**. Used.
3. Global YAML (`global.timeout`) — 30, but plugin-level wins.

For the `page_size` field:
1. Command YAML (`plugins.ecudo.commands.crawl.page_size`) — **50**.
   Used.
2. Lower levels not checked.

### Environment variables

Every field gets an env var named `CRAWLER_<SUFFIX>` where `SUFFIX`
defaults to the uppercase field name. You can override the suffix
via `env="CUSTOM_NAME"` or disable it with `env=False`.

Environment variables sit below YAML but above defaults — they are
a fallback for values not provided via CLI or config file.

## Config Inheritance

Config classes compose via multiple inheritance, which maps cleanly
to argparse argument groups in `--help` output:

```python
class ApiConfig(ConfigBase):
    """Base configuration for API connections."""
    base_url: str = opt(..., description="API base URL")
    timeout: int = opt(15, description="Request timeout in seconds")

class OutputConfig(ConfigBase):
    """Configuration for output settings."""
    output_dir: str = opt("./data", cli=("-o", "--output-dir"))

class ProcessingConfig(ConfigBase):
    """Configuration for parallel processing."""
    concurrency: int = opt(128, description="Number of concurrent workers")
    queue_size: int = opt(1000, description="Size of the processing queue")

class DefaultCrawlConfig(ApiConfig, OutputConfig, ProcessingConfig, kw_only=True):
    """Standard crawl configuration."""
    page_size: int = opt(100, description="Items per API page")
    max_records: int | None = opt(None, cli=("-n", "--max-records"))
    no_url_validation: bool = opt(False, description="Disable URL validation")
```

The schema builder walks the MRO and creates a `ConfigGroup` per
class. Each group becomes an argparse argument group, so `--help`
output is organized by concern (API settings, output settings,
processing settings).

Plugin configs extend further:

```python
class EcudoCrawlConfig(EcudoApiConfig, DefaultCrawlConfig, kw_only=True):
    organization: str = opt(..., cli="organization")
    no_diversity_filter: bool = opt(False)
    diversity_filter: DiversityFilterConfig = opt(
        default_factory=DiversityFilterConfig,
        yaml_key="diversity_filter",
    )
```

## Nested Configs

Dataclass fields that are themselves `ConfigBase` subclasses are
treated as nested configs. They are loaded from YAML only — the
framework does not generate CLI arguments for their inner fields.

```python
class DiversityFilterConfig(ConfigBase):
    """Configuration for Diversity Filter processor."""
    enabled: bool = opt(True, yaml_key="enabled")
    max_similar: int = opt(10, yaml_key="max_similar")
    similarity_threshold: float = opt(0.85, yaml_key="similarity_threshold")
```

In YAML, the nested config appears as a sub-object under the
parent's `yaml_key`:

```yaml
plugins:
  ecudo:
    diversity_filter:
      enabled: true
      max_similar: 5
      similarity_threshold: 0.9
```

This pattern works well for processor-specific tuning knobs that
are too detailed for CLI flags but useful in config files.

## Schema Internals

The schema is built once per class at import time by
`_build_schema()`. It walks the MRO from most specific to most
general class, collecting fields into `ConfigGroup` instances. Each
field becomes a `ConfigFieldInfo` with:

- **`CliInfo`** — pre-computed argparse arguments (flag names,
  kwargs, positional flag, attribute name).
- **`env_var`** — full environment variable name
  (e.g. `CRAWLER_BASE_URL`).
- **`yaml_key`** — key used for YAML lookups.
- **`nested_schema`** — recursive `ConfigSchema` for nested
  dataclass fields.

The `CrawlerPlugin.register_args()` method iterates schema groups
and adds argparse arguments. The `load_config()` method iterates
fields and calls `_resolve_value()` per field, then `_coerce_type()`
to convert string values (from CLI or ENV) to the target type.

<!-- DIAGRAM
What to show: Resolution flow for a single config field — the
  priority chain from CLI through YAML levels to ENV to default,
  showing where each source is checked and the first non-None wins.
Context: Follows the "Resolution Priority" section, visualizes the
  waterfall logic in _resolve_value().
Key participants: CLI args, command YAML, plugin YAML, global YAML,
  ENV var, default value
Related visuals in this doc: none (first diagram)
-->

## Related Documentation

- **[Architecture Overview](_overview.md)** — system layers and data
  flow
- **[Plugin System](plugin-system.md)** — how plugins use config
  for command dispatch
- **[Writing Plugins](../guides/writing-plugins.md)** — practical
  config examples
- **[Glossary](glossary.md#configbase)** — quick definitions
