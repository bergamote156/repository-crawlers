---
title: Schema Authoring
description: >
  How to declare config fields — ConfigBase, opt(), field types, MRO-based
  groups, MutuallyExclusiveGroup, nested configs, and validators. Everything
  that happens at class-creation time.
audience: app-author
source_modules:
  - packages/confline/src/confline/config/base.py
  - packages/confline/src/confline/config/schema.py
  - packages/confline/src/confline/config/types.py
  - packages/confline/src/confline/config/validators.py
source_commits:
  public-data-crawlers: 3c68b70
---

# Schema Authoring

A confline schema is a plain Python class. Subclass `ConfigBase`,
annotate fields with types, assign defaults through `opt()`, and the
framework handles the rest — no `@dataclass` decorator needed, no
runtime build cost after import.

## ConfigBase and opt()
<sub>source: `config/base.py:200–304`, `config/schema.py:108–164`</sub>

`ConfigBase` and `opt()` form a single gesture — every schema uses both:

```python
from confline import ConfigBase, opt

class AppConfig(ConfigBase):
    """One-shot service config — port, workers, debug flag."""

    port: int = opt(8080, description="HTTP port to bind.")
    workers: int = opt(4, description="Worker thread count.")
    debug: bool = opt(False, description="Enable debug logging.")
```

When Python evaluates this class body, the framework auto-applies
`@dataclass(kw_only=True)` and builds a frozen schema from the field
declarations. Secret defaults are never exposed in the auto-generated
`__repr__`.

`opt()` wraps `dataclasses.field()` with confline metadata. Its
parameters:

| Parameter | Effect |
|-----------|--------|
| `default` / `default_factory` | Fallback when no source provides a value |
| `description` | Help text in `--help` and error messages |
| `secret` | Redacted in `__repr__`, `show_config`, errors |
| `count` | Stackable flag (`-vvv`) via `CountAction` |
| `choices` | Explicit allowed values (auto-derived for `Literal`/`Enum`) |
| `validator` | Stateless per-field transform during resolution |
| `excluded_from` | [Source](sources-and-resolution.md#source-protocol) classes that skip this field |
| `deprecated` | Deprecation warning (`True` or message string) |

Mutable defaults (`list`, `dict`, `set`) are auto-wrapped in a
`default_factory` — no need to write `default_factory=list` for an
empty list default.

## Field Types
<sub>source: `config/base.py:128–168`, `resolution/coerce.py:200–226`</sub>

The type annotation drives coercion from raw strings and the `--help`
type description. Built-in types:

- **`str`, `int`, `float`** — strings pass through; numbers cast.
  `bool` accepts `true/false/1/0/yes/no/on/off` and produces a
  `store_true` argparse flag.
- **`Path`** — coerced via `Path()`.
- **`Literal["a", "b"]`** — choices auto-derived; retries with inner
  type when raw value doesn't match directly.
- **`Enum` subclasses** — resolved by value first, by name as fallback.
- **`Optional[T]` / `T | None`** — `None` stripped, field non-required.
- **`list[T]`** — repeatable CLI flag, comma-separated from env, native
  list in YAML.
- **`tuple[X, Y, Z]`** — heterogeneous, per-position coercion via
  `HeterogeneousTupleAction`.
- **`count=True`** — integer incremented per flag occurrence (`-vvv`
  produces `3`).
- **`datetime`, `date`, `time`, `UUID`** — ISO 8601 / standard parsing.

Source-specific naming lives in `Annotated` metadata, not in `opt()`.
[`EnvAlias`](sources-and-resolution.md#source-side-annotations) pins the
environment variable name;
[`YamlPath`](sources-and-resolution.md#source-side-annotations) pins the
YAML key:

```python
api_token: Annotated[str, EnvAlias("MYAPP_API_TOKEN")] = opt(
    description="Auth token.", secret=True,
)
```

### Custom type coercion
<sub>source: `resolution/coerce.py:42–73`, `resolution/coerce.py:157–193`</sub>

For types the app owns, add a `__confline_convert__` classmethod — it
receives a raw string and returns the parsed value, no registration
needed. For external types, call `register_type` at import time with a
parser (must accept already-typed values as passthrough), a `description`
for error messages, and an `example` for `Try one of` hints.

## MRO-Based Groups
<sub>source: `config/base.py:45–93`</sub>

Inherited fields automatically group under the class that declared them
in `--help` — each class in the inheritance chain that contributes
fields becomes a named argument group. The group description is the
class docstring's first paragraph.

```python
class DbConfig(ConfigBase):
    """Database connection settings."""

    host: str = opt("localhost", description="Database hostname.")
    port: int = opt(5432, description="Database TCP port.")

class ServeConfig(ConfigBase):
    """Server runtime options."""

    db: DbConfig = opt(default_factory=DbConfig)
    workers: int = opt(4, description="Number of worker processes.")
```

In `--help`, `host` and `port` appear under **DbConfig**; `workers`
appears under **ServeConfig**. No manual group assignment needed.
When a subclass overrides a field, the most-derived version takes precedence and the parent's duplicate is
skipped.

## Mutually Exclusive Groups
<sub>source: `config/base.py:307–322`, `resolution/mutex.py:32–44`</sub>

Argparse's built-in mutex only sees CLI flags. A YAML file setting both
`port` and `unix_socket` slips through unnoticed. `MutuallyExclusiveGroup`
enforces exclusivity
[post-resolution](sources-and-resolution.md#mutex-enforcement), across
all sources:

```python
class Bind(MutuallyExclusiveGroup, required=False):
    """How the server accepts connections — TCP or Unix socket."""

    port: int = opt(8080, description="TCP port to listen on.")
    unix_socket: Path | None = opt(None, description="Unix socket path.")
```

`required=False` means at most one field may be user-provided (zero is
fine — defaults fill in). `required=True` means exactly one must come
from a non-fallback source.

The distinction is **user-provided vs. default**. The framework reads
each field's [`Provenance`](sources-and-resolution.md#provenance) and
ignores values from `DefaultSource` (where `is_fallback=True`). In the `Bind` example, `port=8080` from the declared
default does not count — only an explicit `--bind.port 9090` or
`MYAPP_BIND__PORT=9090` registers. This catches the cross-source conflict
argparse misses: `MYAPP_BIND__UNIX_SOCKET=/tmp/x myapp serve --bind.port 9090`
raises `MutexViolationError` naming each conflicting source.

## Nested Configs
<sub>source: `config/base.py:147–148`</sub>

When a field's type is a `ConfigBase` subclass, the resolver handles it
recursively. Nested fields surface differently per source:

| Source | Separator | Example for `db.host` |
|--------|-----------|----------------------|
| CLI | dot | `--db.host postgres` |
| Environment | double underscore | `MYAPP_DB__HOST=postgres` |
| YAML | native nesting | `db:\n  host: postgres` |

Nesting composes naturally — a `DbConfig` declared once appears in both
`ServeConfig` and `MigrateConfig`, its fields grouping under **DbConfig**
in each subcommand's `--help`.

> [!IMPORTANT]
> `list[ConfigBase]` fields work only with
> [YAML](sources-and-resolution.md#yamlsource). CLI and environment
> sources are flat key-value spaces and cannot represent lists of
> objects — they report `supports_field = False` and skip the field.

## Validators
<sub>source: `config/validators.py:31–57`</sub>

Three validation layers, each scoped to a different resolution moment:

**`opt(validator=fn)`** runs during resolution, before the instance
exists. Stateless — receives the coerced value, returns the transformed
value. Use for normalization (clamp, lowercase, strip):

```python
port: int = opt(8080, validator=lambda v: max(1, min(v, 65535)))
```

**`@field_validator("field_name")`** runs after instance construction.
Receives `self` and the resolved value, returns it (possibly
transformed). Use when the check needs sibling fields:

```python
@field_validator("port")
def _check_port(self, value: int) -> int:
    if self.host == "localhost" and value < 1024:
        raise ValueError("privileged ports need a real hostname")
    return value
```

**`@model_validator`** runs once after all fields and field validators.
Receives `self`, returns nothing. Use for whole-config invariants:

```python
@model_validator
def _check_resources(self) -> None:
    if self.batch_size > 1000 and self.max_memory_mb < 1024:
        raise ValueError("large batches need at least 1GB of memory")
```

In inheritance hierarchies, most-derived validators override base ones.
Model validators fire in declaration order.
