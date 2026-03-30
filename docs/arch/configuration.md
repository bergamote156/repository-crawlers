# Configuration Framework

## Overview

The crawlers framework provides a declarative configuration system that
automatically generates:
- CLI arguments from config field definitions
- Environment variable bindings
- YAML file loading with hierarchical structure
- Type validation and coercion

Configuration is defined using Python dataclasses with a custom `opt()` field
wrapper that specifies CLI, ENV, and YAML metadata.

## Core Components

### ConfigBase

Base class for all configuration classes. Automatically applies `@dataclass`
decorator and builds configuration schema via `__init_subclass__`.

```python
from crawlers.core.abc.config import ConfigBase, opt

class MyConfig(ConfigBase):
    name: str = opt(..., description="Required field")
    count: int = opt(10, description="Optional with default")
```

### opt() Field Wrapper

The `opt()` function wraps `dataclasses.field()` with additional metadata for
CLI/ENV/YAML bindings:

```python
def opt(
    default: Any = ...,       # Use ... for required fields
    *,
    cli: str | tuple[str, ...] | bool | None = None,
    env: str | bool | None = None,
    yaml_key: str | bool | None = None,
    description: str = "",
    **kwargs,  # Pass to dataclasses.field()
) -> Any
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `default` | `Any` | `...` (required) | Default value. Use `...` (Ellipsis) for required fields. |
| `cli` | `str \| tuple \| bool \| None` | `None` | CLI argument name(s). `None` = auto-generate, `False` = disable. |
| `env` | `str \| bool \| None` | `None` | ENV variable suffix. `None` = auto from field name, `False` = disable. |
| `yaml_key` | `str \| bool \| None` | `None` | YAML key. `None` = use field name, `False` = disable. |
| `description` | `str` | `""` | Help text for CLI and documentation. |

**Auto-generation Rules:**

- **CLI**: `my_field` → `--my-field`
- **ENV**: `my_field` → `CRAWLER_MY_FIELD`
- **YAML**: `my_field` → `my_field`

## Configuration Sources

The framework supports multiple configuration sources with the following
priority (highest first):

```
1. CLI arguments           (--max-records 100)
2. Command YAML section    (plugins.ecudo.commands.crawl.max_records)
3. Plugin YAML section     (plugins.ecudo.max_records)
4. Global YAML section     (global.max_records)
5. Environment variables   (CRAWLER_MAX_RECORDS)
6. Default values          (opt(100, ...))
```

### YAML Structure

```yaml
global:
  # Settings shared across all plugins
  timeout: 30
  max_retries: 5

plugins:
  ecudo:
    # Plugin-level defaults
    base_url: "http://central.ecudo.pl"

    commands:
      crawl:
        # Command-specific settings
        page_size: 500
        processors:
          url_validator:
            enabled: true
```

## Built-in Config Classes

The following base config classes are defined in `crawlers.core.default.config`:

```python
class ApiConfig(ConfigBase):
    base_url: str = opt(..., description="API base URL")
    timeout: int = opt(15, description="Request timeout in seconds")
    max_retries: int = opt(3, description="Maximum retry attempts")

class OutputConfig(ConfigBase):
    output_dir: str = opt("./data", cli=("-o", "--output-dir"),
                          description="Output directory for crawled data")

class ProcessingConfig(ConfigBase):
    concurrency: int = opt(128, description="Number of concurrent workers")
    queue_size: int = opt(1000, description="Size of the processing queue")

class DefaultCrawlConfig(ApiConfig, OutputConfig, ProcessingConfig, kw_only=True):
    page_size: int = opt(100, description="Items per API page")
    max_records: int | None = opt(None, cli=("-n", "--max-records"),
                                  description="Maximum number of items to fetch")
    no_url_validation: bool = opt(False, description="Disable URL validation")
```

Plugin-specific config classes should inherit from `DefaultCrawlConfig` (or
its components) and add source-specific fields.

## Field Types

### Basic Types

```python
class MyConfig(ConfigBase):
    name: str = opt("default", description="String field")
    count: int = opt(10, description="Integer field")
    ratio: float = opt(0.5, description="Float field")
    enabled: bool = opt(False, description="Boolean field")
```

**Boolean handling:**
- CLI: Uses `action="store_true"` (flag-style)
- ENV/YAML: Accepts `"true"`, `"1"`, `"yes"`, `"on"` (case-insensitive)

### Optional Fields

```python
class MyConfig(ConfigBase):
    # Required field (no default)
    organization: str = opt(..., description="Must be provided")

    # Optional with None default
    max_records: int | None = opt(None, description="No limit if None")
```

### Nested Configurations

Configurations can contain nested config objects. Nested configs are loaded
from YAML only (not CLI):

```python
class URLValidatorConfig(ConfigBase):
    enabled: bool = opt(True)

class DiversityFilterConfig(ConfigBase):
    enabled: bool = opt(True)
    max_similar: int = opt(10)
    similarity_threshold: float = opt(0.85)

class ProcessorsConfig(ConfigBase):
    url_validator: URLValidatorConfig = opt(default_factory=URLValidatorConfig)
    diversity_filter: DiversityFilterConfig = opt(default_factory=DiversityFilterConfig)

class CrawlConfig(DefaultCrawlConfig, kw_only=True):
    processors: ProcessorsConfig = opt(default_factory=ProcessorsConfig)
```

**YAML representation:**

```yaml
plugins:
  myplugin:
    processors:
      url_validator:
        enabled: true
      diversity_filter:
        enabled: true
        max_similar: 5
```

## CLI Argument Patterns

### Positional Arguments

For positional CLI arguments, explicitly specify the CLI name without dashes:

```python
organization: str = opt(
    ...,
    cli="organization",  # Positional arg (no dashes)
    description="Organization ID",
)
```

**Usage:** `crawlers ecudo crawl iopan`

### Optional Arguments with Aliases

```python
max_records: int | None = opt(
    None,
    cli=("-n", "--max-records"),  # Short and long form
    description="Maximum records",
)
```

**Usage:** `crawlers ecudo crawl iopan -n 100` or `--max-records 100`

### Flag Arguments (Boolean)

```python
no_url_validation: bool = opt(False, description="Disable URL validation")
```

**Generated CLI:** `--no-url-validation` (store_true action)

### Disabling CLI

For complex fields (nested objects, GeoJSON, etc.) that should only be
configured via YAML:

```python
intersects: dict | None = opt(
    None,
    cli=False,  # No CLI argument
    yaml_key="intersects",
    description="GeoJSON geometry filter",
)
```

## Configuration Inheritance

Config classes support inheritance through Python class hierarchy:

```python
from crawlers.core.default.config import ApiConfig, DefaultCrawlConfig
from crawlers.core.abc.config import ConfigBase, opt

class EcudoApiConfig(ApiConfig):
    base_url: str = opt("http://central.ecudo.pl", description="Ecudo API URL")

class EcudoCrawlConfig(EcudoApiConfig, DefaultCrawlConfig, kw_only=True):
    organization: str = opt(..., cli="organization", description="Organization ID")
    processors: EcudoProcessorsConfig = opt(default_factory=EcudoProcessorsConfig)
```

**CLI Help Output (grouped by inheritance):**

```
EcudoCrawlConfig:
  organization          Organization ID

DefaultCrawlConfig:
  -n, --max-records     Maximum records
  --no-url-validation   Disable URL validation

EcudoApiConfig:
  --base-url            Ecudo API base URL

ApiConfig:
  --max-retries MAX_RETRIES
                        Maximum retry attempts
  --timeout TIMEOUT     Request timeout in seconds

OutputConfig:
  -o, --output-dir      Output directory

ProcessingConfig:
  --concurrency         Concurrent workers
```

## Post-initialization Validation

Use `__post_init__` for validation and transformation:

```python
class EcudoCrawlConfig(DefaultCrawlConfig, kw_only=True):
    organization: str = opt(..., cli="organization")

    def __post_init__(self):
        if not self.organization or self.organization.isspace():
            raise ValueError("Organization cannot be empty")
        self.organization = self.organization.strip().lower()
```

## Helper Methods

Add methods to configs for derived values:

```python
class EcudoCrawlConfig(DefaultCrawlConfig, kw_only=True):
    processors: EcudoProcessorsConfig = opt(default_factory=EcudoProcessorsConfig)

    def get_url_validator_enabled(self) -> bool:
        """CLI flag overrides nested config."""
        if self.no_url_validation:
            return False
        return self.processors.url_validator.enabled

    def get_diversity_filter_enabled(self) -> bool:
        return self.processors.diversity_filter.enabled
```

## Schema Introspection

The framework builds a `ConfigSchema` at class definition time, accessible
via `__config_schema__`:

```python
schema = MyConfig.__config_schema__

for field_info in schema.all_fields():
    print(f"{field_info.name}: {field_info.field_type}")
    print(f"  CLI: {field_info.cli}")
    print(f"  ENV: {field_info.env_var}")
    print(f"  Required: {field_info.required}")
```

## Complete Example

```python
from crawlers.core.abc.config import ConfigBase, opt
from crawlers.core.default.config import ApiConfig, DefaultCrawlConfig


class EODCApiConfig(ApiConfig):
    """EODC API configuration."""
    base_url: str = opt("https://services.sentinel-hub.com", description="EODC API URL")


class EODCCrawlConfig(EODCApiConfig, DefaultCrawlConfig, kw_only=True):
    """Full crawl configuration for EODC."""

    # Positional argument
    collections: list[str] = opt(..., cli="collections", description="Collection IDs to crawl")

    # Optional with aliases
    datetime: str | None = opt(
        None,
        cli="--datetime",
        description="Date range filter (ISO 8601 interval)",
    )

    # YAML-only (complex type)
    intersects: dict | None = opt(
        None,
        cli=False,
        description="GeoJSON geometry filter",
    )

    def __post_init__(self):
        if not self.collections:
            raise ValueError("At least one collection required")
```

**Usage:**

```bash
# CLI only
crawlers eodc crawl s1-grd,s2-l1c -n 100 -o ./out

# With config file
crawlers -c config.yaml eodc crawl s1-grd

# Environment variable
CRAWLER_TIMEOUT=30 crawlers eodc crawl s1-grd
```
