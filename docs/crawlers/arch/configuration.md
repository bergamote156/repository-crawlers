---
title: Configuration System
description: >
  How config fields are declared once and resolved from multiple
  sources (CLI, YAML, ENV) at runtime. Covers ConfigBase, opt(),
  schema internals, resolution priority, config inheritance, and
  nested configs.
topic: crawlers/arch/configuration
audience: internal-developer-onboarding
generated: 2026-04-01
last_reviewed: 2026-04-04
source_modules:
  - crawlers/core/config.py
  - crawlers/core/plugin.py
  - crawlers/default/config.py
  - crawlers/plugins/ecudo/config.py
  - crawlers/plugins/eodc/config.py
source_commits:
  public-data-crawlers: bbd9be2e7
status: draft
---

# Configuration System

<sub>📄 `crawlers/core/plugin.py:183-308`</sub>

Declare a config field once — as an annotated dataclass field with
`opt()` — and the framework gives you CLI argument parsing, YAML
file loading, environment variable support, and help text generation
for free. At runtime, values from all sources merge according to a
fixed [priority order](#resolution-priority): CLI wins over YAML,
YAML wins over ENV, ENV wins over defaults. You never write argument
parsing code or config-loading boilerplate.

```mermaid
graph TB
    field["📝 field declared with opt·&#41;"]

    field --> cli{"🖥️ CLI arg\nprovided?"}
    cli -->|yes| cli_val["✅ use CLI value"]
    cli -->|no| cmd_yaml{"📄 Command YAML\nprovided?"}

    subgraph yaml_hierarchy["📄 YAML file structure"]
        direction TB
        global_sec["global.‹key›"]
        plugin_sec["plugins.‹name›.‹key›"]
        cmd_sec["plugins.‹name›.commands.‹cmd›.‹key›"]
    end

    cmd_yaml -->|yes| cmd_val["✅ use Command YAML value"]
    cmd_yaml -->|no| plugin_yaml{"📄 Plugin YAML\nprovided?"}
    plugin_yaml -->|yes| plugin_val["✅ use Plugin YAML value"]
    plugin_yaml -->|no| global_yaml{"📄 Global YAML\nprovided?"}
    global_yaml -->|yes| global_val["✅ use Global YAML value"]
    global_yaml -->|no| env{"🌐 ENV var\nprovided?"}
    env -->|yes| env_val["✅ use ENV value"]
    env -->|no| default["⚙️ use opt·&#41; default"]

    cmd_sec -.->|feeds| cmd_yaml
    plugin_sec -.->|feeds| plugin_yaml
    global_sec -.->|feeds| global_yaml

    classDef decision fill:#FFD700,stroke:#F08C00,color:#000
    classDef resolved fill:#95D5B2,stroke:#2D6A4F,color:#000
    classDef source fill:#E6E6FA,stroke:#5B4B8A,color:#000
    classDef start fill:#4ECDC4,stroke:#0B7285,color:#000

    class cli,cmd_yaml,plugin_yaml,global_yaml,env decision
    class cli_val,cmd_val,plugin_val,global_val,env_val,default resolved
    class global_sec,plugin_sec,cmd_sec source
    class field start
```

## ConfigBase and opt()

<sub>📄 `crawlers/core/config.py:21-52`</sub>

Every config class inherits from
[**ConfigBase**](glossary.md#configbase). The base class intercepts
subclass creation via `__init_subclass__`: it applies `@dataclass`
and builds a `ConfigSchema` automatically. You never call
`@dataclass` yourself.

<sub>📄 `crawlers/core/config.py:54-111`</sub>

Fields use `opt()` instead of `dataclasses.field()` to attach
metadata describing how each value can be provided:

```python
class ApiConfig(ConfigBase):
    """Base configuration for API connections."""

    base_url: str = opt(..., description="API base URL")
    timeout: int = opt(15, description="Request timeout in seconds")
    max_retries: int = opt(3, description="Maximum retry attempts")
```

### opt() Parameters

| Parameter | Type | Default | Effect |
|-----------|------|---------|--------|
| `default` | any | `...` (required) | Default value. `...` means the field is required. |
| `cli` | `str \| tuple \| False \| None` | `None` | CLI flag name(s). `None` auto-generates from field name (`my_field` → `--my-field`). `False` disables CLI. |
| `env` | `str \| False \| None` | `None` | ENV var suffix. `None` auto-generates (`my_field` → `CRAWLER_MY_FIELD`). `False` disables ENV. |
| `yaml_key` | `str \| False \| None` | `None` | YAML key. `None` uses the field name. `False` disables YAML loading. |
| `description` | `str` | `""` | Help text for CLI `--help` and documentation. |

### Field Type Handling

<sub>📄 `crawlers/core/config.py:272-283` · `crawlers/core/config.py:286-330`</sub>

The schema builder inspects field type annotations to configure
argparse correctly:

- **`bool`** — generates `action="store_true"` (flag without value).
- **`int`, `float`, `str`** — passes the corresponding `type=` to
  argparse for automatic coercion.
- **`Optional[X]`** / **`X | None`** — unwrapped to `X` for type
  handling; the field is not treated as required.
- **Nested dataclass** — the field gets a recursive `ConfigSchema`.
  Nested configs are YAML-only (no CLI generation). See
  [Nested Configs](#nested-configs).

### Positional Arguments

<sub>📄 `crawlers/core/config.py:303-305`</sub>

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

<sub>📄 `crawlers/core/plugin.py:274-308`</sub>

When multiple sources provide a value for the same field, the
highest-priority source wins:

1. **CLI arguments** — `--base-url https://...`
2. **Command YAML** —
   `plugins.<plugin>.commands.<command>.<key>`
3. **Plugin YAML** — `plugins.<plugin>.<key>`
4. **Global YAML** — `global.<key>`
5. **Environment variables** — `CRAWLER_<SUFFIX>`
6. **Default values** — from the `opt()` call

### How YAML Lookup Works

<sub>📄 `crawlers/core/plugin.py:208-223`</sub>

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

### Environment Variables

<sub>📄 `crawlers/core/config.py:249-252`</sub>

Every field gets an env var named `CRAWLER_<SUFFIX>` where `SUFFIX`
defaults to the uppercase field name. You can override the suffix
via `env="CUSTOM_NAME"` or disable it with `env=False`.

Environment variables sit below YAML but above defaults — they are
a fallback for values not provided via CLI or config file.

## Config Inheritance

<sub>📄 `crawlers/default/config.py:17-52`</sub>

Config classes compose via multiple inheritance, which maps cleanly
to argparse argument groups in `--help` output:

```mermaid
graph TB
    CB["🏗️ ConfigBase"]

    CB --> AC["🌐 ApiConfig\nbase_url · timeout · max_retries"]
    CB --> OC["💾 OutputConfig\noutput_dir"]
    CB --> PC["⚙️ ProcessingConfig\nconcurrency · queue_size"]

    AC --> DCC["📋 DefaultCrawlConfig\npage_size · max_records · no_url_validation"]
    OC --> DCC
    PC --> DCC

    DCC --> ECC["🔌 EcudoCrawlConfig\norganization · no_diversity_filter\ndiversity_filter ·nested·"]
    DCC --> EODC["🔌 EODCCrawlConfig\ncollections · intersects · datetime_range"]

    classDef core fill:#E6E6FA,stroke:#5B4B8A,color:#000
    classDef mixin fill:#A8DADC,stroke:#1864AB,color:#000
    classDef framework fill:#4ECDC4,stroke:#0B7285,color:#000
    classDef plugin fill:#FFE4B5,stroke:#E8890C,color:#000

    class CB core
    class AC,OC,PC mixin
    class DCC framework
    class ECC,EODC plugin
```

```python
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

Plugin configs extend further — adding source-specific fields while
inheriting all the standard ones:

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

## Schema Internals (Framework Maintainers)

<sub>📄 `crawlers/core/config.py:116-165`</sub>

> The following section is relevant if you're modifying the config
> framework itself. Skip if you're writing plugins.

The schema is built once per class at import time by
`_build_schema()`. It walks the MRO from most specific to most
general class, collecting fields into `ConfigGroup` instances.

```mermaid
classDiagram
    class ConfigSchema {
        config_class
        groups : ConfigGroup[]
    }

    class ConfigGroup {
        name
        description
        fields : ConfigFieldInfo[]
    }

    class ConfigFieldInfo {
        name
        field_type
        description
        default
        required
        cli : CliInfo | None
        env_var : str | None
        yaml_key : str | None
        nested_schema : ConfigSchema | None
    }

    class CliInfo {
        names
        kwargs
        is_positional
        attr_name
    }

    ConfigSchema "1" --> "0..*" ConfigGroup : groups
    ConfigGroup "1" --> "0..*" ConfigFieldInfo : fields
    ConfigFieldInfo --> CliInfo : cli
    ConfigFieldInfo --> ConfigSchema : nested_schema

    style ConfigSchema fill:#4ECDC4,stroke:#0B7285,color:#000
    style ConfigGroup fill:#A8DADC,stroke:#1864AB,color:#000
    style ConfigFieldInfo fill:#E6E6FA,stroke:#5B4B8A,color:#000
    style CliInfo fill:#FFE4B5,stroke:#E8890C,color:#000
```

<sub>📄 `crawlers/core/config.py:167-204`</sub>

Each field becomes a `ConfigFieldInfo` with:

- **`CliInfo`** — pre-computed argparse arguments (flag names,
  kwargs, positional flag, attribute name).
- **`env_var`** — full environment variable name
  (e.g. `CRAWLER_BASE_URL`).
- **`yaml_key`** — key used for YAML lookups.
- **`nested_schema`** — recursive `ConfigSchema` for nested
  dataclass fields.

<sub>📄 `crawlers/core/plugin.py:111-161`</sub>

The `CrawlerPlugin.register_args()` method iterates schema groups
and adds argparse arguments. The `load_config()` method iterates
fields, calls `_resolve_value()` per field to apply the
[resolution priority](#resolution-priority), then `_coerce_type()`
to convert string values (from CLI or ENV) to the target type.
