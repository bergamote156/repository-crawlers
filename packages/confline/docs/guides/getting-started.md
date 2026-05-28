---
title: "Getting Started with confline"
description: >
  Build a single-config CLI app from scratch — declare fields with
  ConfigBase and opt(), assemble a source chain, and load config with
  operator-friendly error handling.
audience: app-author
source_modules:
  - packages/confline/examples/single_config_app.py
  - packages/confline/examples/demo_app.py
  - packages/confline/src/confline/__init__.py
source_commits:
  public-data-crawlers: 3c68b70
---

# Getting Started with confline

Build a CLI tool that loads configuration from environment variables,
command-line flags, YAML files, and defaults -- with zero boilerplate
for argument parsing, type coercion, and error messages.

> [!TIP]
> **Quick Path** -- if you already know dataclasses and just want
> the recipe:
>
> 1. Subclass `ConfigBase`, declare fields with `opt()`
> 2. Build a source list:
>    `[EnvSource(...), CliSource.from_argv(...), DefaultSource()]`
> 3. Call `load_or_exit(MyConfig, sources=sources, prog="myapp")`
> 4. See
>    [`examples/single_config_app.py`](../../examples/single_config_app.py)
>    for the complete implementation.

> [!NOTE]
> **Prerequisites:**
> - Python 3.12+
> - confline installed (`pip install -e packages/confline`)
> - Familiarity with Python dataclasses and type annotations


## Define Your Config

A confline config is a plain Python class that subclasses
[`ConfigBase`](../design/schema.md#configbase-and-opt). You declare
fields with type annotations and use `opt()` to attach metadata --
default value, description, whether the field is secret, and so on. No
`@dataclass` decorator needed; `ConfigBase` applies it automatically
and builds an internal schema at class-creation time.

```python
from confline import ConfigBase, opt

class AppConfig(ConfigBase):
    """One-shot service config -- port, workers, debug flag."""

    port: int = opt(8080, description="HTTP port to bind.")
    workers: int = opt(4, description="Worker thread count.")
    debug: bool = opt(False, description="Enable debug logging.")
```

The first positional argument to `opt()` is the default value. Fields
without a default are required -- resolution fails if no source
provides them. The `description` feeds into `--help` automatically.

> [!TIP]
> **Source:** `packages/confline/examples/single_config_app.py:55-61`


## Assemble Sources

Sources tell confline *where* to look for values. You build a list and
pass it to the loader. Order matters: the first source that provides a
value for a field wins.

```python
import os
import sys
from pathlib import Path
from confline import CliSource, EnvSource, YamlSource, DefaultSource

yaml_path = Path("config.yaml")
sources = [
    EnvSource(os.environ, prefix="MYAPP_"),
    CliSource.from_argv(AppConfig, sys.argv[1:]),
    YamlSource.from_files([yaml_path]) if yaml_path.exists() else None,
    DefaultSource(),
]
sources = [s for s in sources if s is not None]
```

This ordering -- env, cli, yaml, default -- is a "container-friendly"
precedence: env vars set by an orchestrator override everything else,
CLI flags serve as ad-hoc overrides during debugging, and `opt()`
defaults are the floor. If you want CLI flags to win instead, put
`CliSource` first -- or use `load_default()`, which does exactly that.
See [Sources and Resolution](../design/sources-and-resolution.md#the-source-chain)
for the full picture on chain ordering.

`EnvSource` maps field names to env vars by uppercasing and prepending
the prefix: `port` becomes `MYAPP_PORT`, `workers` becomes
`MYAPP_WORKERS`.

> [!TIP]
> **Source:** `packages/confline/examples/single_config_app.py:64-71`


## Load and Use

With the config class and sources ready, one call resolves everything:

```python
from confline import load_or_exit

config = load_or_exit(AppConfig, sources=sources, prog="myapp")

print(f"port={config.port} (from {config.source_of('port').label})")
print(f"workers={config.workers} (from {config.source_of('workers').label})")
print(f"debug={config.debug} (from {config.source_of('debug').label})")
```

`load_or_exit` walks the source chain for every field, coerces raw
strings to the declared type, and runs validators. On failure -- a
missing required field, a bad value, a mutex violation -- it renders
an operator-friendly message to stderr and raises `SystemExit` with a
typed exit code (64 for usage errors, 65 for bad data). No try/except
needed for the common case.

`source_of()` returns a `Provenance` object so you can confirm exactly
which source provided each value.

> [!TIP]
> **Source:** `packages/confline/src/confline/resolution/api.py:68-92`


## See It Work

Save the combined code as `myapp.py` and run through these scenarios.

**Defaults only** -- every value comes from `DefaultSource`:

```console
$ python myapp.py
port=8080 (from default)
workers=4 (from default)
debug=False (from default)
```

**CLI override** -- `--port` wins over the default:

```console
$ python myapp.py --port 9090
port=9090 (from cli --port)
workers=4 (from default)
debug=False (from default)
```

**Env override** -- env has higher precedence than CLI in this chain,
so `MYAPP_PORT` wins even when `--port` is also passed:

```console
$ MYAPP_PORT=7070 python myapp.py --port 9090
port=7070 (from env MYAPP_PORT)
workers=4 (from default)
debug=False (from default)
```

**Error rendering** -- a non-integer value for `port` produces a
structured diagnostic:

```console
$ MYAPP_PORT=abc python myapp.py
myapp: invalid value for MYAPP_PORT

  field:    port
  given:    'abc'
  source:   env MYAPP_PORT
  expected: int

Run `myapp --help` for full options.
```

The error message shows the field path, the raw value, which source it
came from, and what type was expected. Operators get actionable
diagnostics without reading Python tracebacks.


## Next Steps

- **Add YAML config support** -- `YamlSource.from_files` loads values
  from a YAML file. The
  [`single_config_app.py`](../../examples/single_config_app.py) example
  already includes the conditional pattern.
- **Build a multi-command app** --
  [Building a Multi-Command App](command-app.md) walks through
  `CommandApp` with `@command` — subcommand dispatch, nested configs,
  mutex groups, async dispatch, and custom source chains.
- **Add field types** -- `Literal`, `Path`, `list[str]`, and nested
  `ConfigBase` subclasses all work as field types with
  [automatic coercion](../design/schema.md#field-types).
- **Add validation** --
  [`@field_validator` and `@model_validator`](../design/schema.md#validators)
  decorators run custom checks after coercion.
