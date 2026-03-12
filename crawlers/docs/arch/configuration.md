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
    invalid_url_log: str | None = opt("invalid_urls.jsonl")

class ProcessorsConfig(ConfigBase):
    url_validator: URLValidatorConfig = opt(
        default_factory=URLValidatorConfig,
        yaml_key="url_validator",
    )

class CrawlConfig(ConfigBase):
    processors: ProcessorsConfig = opt(
        default_factory=ProcessorsConfig,
    )
```

**YAML representation:**

```yaml
plugins:
  myplugin:
    processors:
      url_validator:
        enabled: true
        invalid_url_log: "invalid.jsonl"
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
verbose: bool = opt(False, description="Enable verbose output")
```

**Generated CLI:** `--verbose` (store_true action)

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
# Base configs in crawlers.core.config
class ApiConfig(ConfigBase):
    base_url: str = opt(..., description="API base URL")
    timeout: int = opt(15, description="Timeout in seconds")
    max_retries: int = opt(3, description="Max retry attempts")

class OutputConfig(ConfigBase):
    output_dir: str = opt("./data", cli=("-o", "--output-dir"))

class ProcessingConfig(ConfigBase):
    concurrency: int = opt(128, description="Concurrent workers")

class BaseCrawlConfig(ApiConfig, OutputConfig, ProcessingConfig):
    """Base for all crawl commands - combines all base configs."""

# Plugin-specific config
class EcudoCrawlConfig(EcudoApiConfig, BaseCrawlConfig, kw_only=True):
    organization: str = opt(..., cli="organization")
    max_records: int | None = opt(None, cli=("-n", "--max-records"))
```

**CLI Help Output (grouped by inheritance):**

```
EcudoCrawlConfig:
  organization          Organization ID
  -n, --max-records     Maximum records

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
class EcudoCrawlConfig(BaseCrawlConfig):
    organization: str = opt(..., cli="organization")
    
    def __post_init__(self):
        if not self.organization or self.organization.isspace():
            raise ValueError("Organization cannot be empty")
        
        # Normalize
        self.organization = self.organization.strip().lower()
```

## Helper Methods

Add methods to configs for derived values:

```python
class EcudoCrawlConfig(BaseCrawlConfig):
    no_url_validation: bool = opt(False, description="Disable URL validation")
    processors: ProcessorsConfig = opt(default_factory=ProcessorsConfig)
    
    def get_url_validator_enabled(self) -> bool:
        """CLI flag overrides nested config."""
        if self.no_url_validation:
            return False
        return self.processors.url_validator.enabled
```

## Schema Introspection

The framework builds a `ConfigSchema` at class definition time, accessible 
via `__config_schema__`:

```python
schema = MyConfig.__config_schema__

# Iterate all fields
for field_info in schema.all_fields():
    print(f"{field_info.name}: {field_info.field_type}")
    print(f"  CLI: {field_info.cli}")
    print(f"  ENV: {field_info.env_var}")
    print(f"  Required: {field_info.required}")
```

**ConfigFieldInfo attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Field name |
| `field_type` | `type` | Actual type (unwrapped from Optional) |
| `description` | `str` | Help text |
| `default` | `Any` | Default value or factory |
| `required` | `bool` | True if no default |
| `cli` | `CliInfo \| None` | CLI argument info |
| `env_var` | `str \| None` | Full ENV var name |
| `yaml_key` | `str \| None` | YAML key |
| `nested_schema` | `ConfigSchema \| None` | Schema for nested configs |

## Complete Example

```python
from crawlers.core.config import ApiConfig, BaseCrawlConfig, ConfigBase, opt


class EcudoApiConfig(ApiConfig):
    """Ecudo API configuration."""
    base_url: str = opt("http://central.ecudo.pl", description="Ecudo API URL")


class URLValidatorConfig(ConfigBase):
    """URL validator settings."""
    enabled: bool = opt(True)
    invalid_url_log: str | None = opt("invalid_urls.jsonl")


class ProcessorsConfig(ConfigBase):
    """Processor configurations."""
    url_validator: URLValidatorConfig = opt(default_factory=URLValidatorConfig)


class EcudoCrawlConfig(EcudoApiConfig, BaseCrawlConfig, kw_only=True):
    """Full crawl configuration."""
    
    # Positional argument
    organization: str = opt(..., cli="organization", description="Organization ID")
    
    # Optional with aliases
    max_records: int | None = opt(None, cli=("-n", "--max-records"))
    
    # CLI flag to override nested config
    no_url_validation: bool = opt(False, description="Disable URL validation")
    
    # Nested config (YAML only)
    processors: ProcessorsConfig = opt(default_factory=ProcessorsConfig)
    
    def __post_init__(self):
        self.organization = self.organization.strip().lower()
    
    def get_url_validator_enabled(self) -> bool:
        if self.no_url_validation:
            return False
        return self.processors.url_validator.enabled
```

**Usage:**

```bash
# CLI only
crawlers ecudo crawl iopan -n 100 --output-dir ./out

# With config file
crawlers ecudo -c config.yaml crawl iopan

# Environment variable
CRAWLER_TIMEOUT=30 crawlers ecudo crawl iopan
```
