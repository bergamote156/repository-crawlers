---
title: "Building a Multi-Command App"
description: >
  Build a CLI tool with multiple subcommands using CommandApp and
  @command — per-command configs, naming conventions, aliases, async
  dispatch, source chain customization, and meta-flag hooks.
audience: app-author
source_modules:
  - packages/confline/examples/demo_app.py
  - packages/confline/src/confline/commands.py
source_commits:
  public-data-crawlers: 3c68b70
---

# Building a Multi-Command App

The [Getting Started](getting-started.md) guide builds a single-config
app where you assemble sources and call `load_or_exit` by hand.
`CommandApp` handles all of that for you — subcommand dispatch, source
chain assembly, error rendering, and `--help` generation. You subclass
it, decorate methods with `@command`, and call `run()`.

```python
from confline import CommandApp, ConfigBase, command, opt

class ServeConfig(ConfigBase):
    """Server runtime options."""
    port: int = opt(8080, description="HTTP port to bind.")
    workers: int = opt(4, description="Number of worker processes.")

class MyApp(CommandApp):
    prog = "myapp"
    env_prefix = "MYAPP_"

    @command
    def serve(self, config: ServeConfig) -> int:
        """Start the HTTP server."""
        print(f"Listening on port {config.port}")
        return 0

if __name__ == "__main__":
    raise SystemExit(MyApp().run())
```

```console
$ python myapp.py serve --port 9090
Listening on port 9090

$ python myapp.py --help
usage: myapp [-h] [-c CONFIG] {serve} ...

$ python myapp.py serve --help
usage: myapp serve [-h] [--port PORT] [--workers WORKERS]
```

Four class attributes control the app's identity:

| Attribute | Effect |
|-----------|--------|
| `prog` | Program name in `--help` headers and error messages |
| `description` | One-liner shown in top-level `--help` |
| `env_prefix` | Prefix for `EnvSource` key derivation (`MYAPP_PORT`) |
| `config_option` | CLI flag(s) for YAML config files; default `("-c", "--config")`, set `()` to disable |


## Multiple Commands

Each `@command` method gets its own config class. The config class is
inferred from the type annotation — the first `ConfigBase` subclass
in the method's signature.

```python
class MigrateConfig(ConfigBase):
    """Migration settings."""
    schema_dir: Path = opt(description="Directory with migration files.")
    dry_run: bool = opt(False, description="Plan without applying.")

    
class MyApp(CommandApp):
    prog = "myapp"
    env_prefix = "MYAPP_"

    @command
    def serve(self, config: ServeConfig) -> int:
        """Start the HTTP server."""
        ...

    @command
    def migrate(self, config: MigrateConfig) -> int:
        """Run pending database migrations."""
        ...
```

Each command appears as a subparser in `--help`. Fields from
`ServeConfig` only show up under `myapp serve --help`; fields from
`MigrateConfig` only under `myapp migrate --help`.


## Naming and Aliases

Method names automatically become kebab-case subcommand names:
`list_orgs` becomes `list-orgs`. This matches Click and Typer
conventions. Override with `name=` when you need something different:

```python
@command(name="list-orgs")
def list_organizations(self, config: ListConfig) -> int:
    """List all available organizations."""
    ...
```

Add aliases for short forms:

```python
@command(aliases=["m"])
def migrate(self, config: MigrateConfig) -> int:
    """Run pending database migrations."""
    ...
```

Now both `myapp migrate` and `myapp m` dispatch to the same handler.
Alias collisions with other command names or aliases are caught at
class-creation time — the app never starts with an ambiguous dispatch
table.


## Shared Config via Nesting

Commands that share a subset of configuration — database credentials,
HTTP settings — declare the shared part as a nested `ConfigBase`:

```python
class DbConfig(ConfigBase):
    """Database connection settings."""
    host: str = opt("localhost", description="Database hostname.")
    port: int = opt(5432, description="Database TCP port.")
    password: str = opt("changeme", description="Database password.", secret=True)


class ServeConfig(ConfigBase):
    """Server options."""
    db: DbConfig = opt(default_factory=DbConfig)
    workers: int = opt(4, description="Worker processes.")


class MigrateConfig(ConfigBase):
    """Migration options."""
    db: DbConfig = opt(default_factory=DbConfig)
    schema_dir: Path = opt(description="Migration file directory.")
```

The `DbConfig` fields surface through all sources with path-aware
naming:

| Source | Key for `db.host` |
|--------|-------------------|
| CLI | `--db.host localhost` |
| Env | `MYAPP_DB__HOST=localhost` |
| YAML | `db:\n  host: localhost` |

In `--help`, `host`, `port`, and `password` group under **DbConfig**
automatically — no manual group assignment needed.


## Custom Source Chains

The default source chain is CLI → env → YAML → defaults. Override
`build_sources` to change precedence, add sources, or scope YAML
loading per command:

```python
class MyApp(CommandApp):
    def build_sources(self, parsed, command):
        sources = [
            EnvSource(os.environ, prefix=self.env_prefix),   # env wins
            CliSource(parsed),                               # CLI second
        ]
        config_files = self.discover_config_files(parsed)
        if config_files:
            sources.append(YamlSource.from_files(config_files))
        sources.append(DefaultSource())
        return sources
```

> [!IMPORTANT]
> When overriding `build_sources`, override `_label_sources` too.
> `_label_sources` builds the same chain shape without runtime values
> — its only job is powering `--help` rendering. A mismatch means
> `--help` advertises source keys the resolver never reads.


## Full Example

See [`examples/demo_app.py`](../../examples/demo_app.py) for a
working app with two commands, nested configs, a mutex group,
source-side annotations (`EnvAlias`, `YamlPath`), and provenance
inspection. Run it to see every error rendering path:

```console
# Help
python demo_app.py --help
python demo_app.py serve --help

# Cross-source mutex violation
MYAPP_API_TOKEN=t MYAPP_BIND__UNIX_SOCKET=/tmp/x python demo_app.py serve --bind.port 9090

# Coercion error from env
MYAPP_API_TOKEN=t MYAPP_BIND__PORT=abc python demo_app.py serve

# Missing required field
python demo_app.py migrate

# Did-you-mean for unknown subcommand
python demo_app.py migate
```
