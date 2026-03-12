# Plugin System

## Overview

The crawlers framework uses a plugin architecture where each data source 
(Ecudo, EODC, etc.) is implemented as a plugin. Plugins define commands 
using decorators, and the framework automatically handles:

- CLI argument parsing from config schemas
- Configuration loading from CLI/YAML/ENV
- Command dispatch to appropriate methods

## Core Components

### CrawlerPlugin Base Class

All plugins inherit from `CrawlerPlugin`:

```python
from crawlers.core.plugin import CrawlerPlugin, command

class MyPlugin(CrawlerPlugin):
    name = "myplugin"           # CLI subcommand name
    description = "My crawler"   # Help text
    
    @command("crawl", MyCrawlConfig, help="Run crawler")
    async def run_crawl(self, config: MyCrawlConfig) -> None:
        ...
```

**Required attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Plugin identifier, used as CLI subcommand |
| `description` | `str` | Short description for help text |

### @command Decorator

Registers a method as a CLI command:

```python
@command(
    name: str,                    # Command name (e.g. "crawl")
    config: type[ConfigBase],     # Config class for this command
    *,
    help: str = "",               # Help text
)
```

**Example:**

```python
@command("list-orgs", EcudoApiConfig, help="List available organizations")
async def list_organizations(self, config: EcudoApiConfig) -> None:
    ...
```

**Generated CLI:** `crawlers ecudo list-orgs [OPTIONS]`

## Plugin Lifecycle

### 1. Registration

Plugins are instantiated and registered in `crawlers/plugins/__init__.py`:

```python
from crawlers.plugins.ecudo.plugin import EcudoPlugin
from crawlers.plugins.eodc.plugin import EODCPlugin

REGISTERED_PLUGINS = [
    EcudoPlugin(),
    EODCPlugin(),
]
```

### 2. Command Collection

When a plugin class is defined, `__init_subclass__` automatically collects 
all `@command`-decorated methods:

```python
class CrawlerPlugin(ABC):
    _commands: dict[str, CommandDef]
    
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._commands = {}
        
        for attr_name in dir(cls):
            method = getattr(cls, attr_name, None)
            if callable(method) and hasattr(method, "_command_def"):
                cmd_def = method._command_def
                cls._commands[cmd_def.name] = cmd_def
```

### 3. CLI Generation

The main CLI (`crawlers/cli.py`) creates subparsers for each plugin and 
delegates argument registration:

```python
for plugin in REGISTERED_PLUGINS:
    plugin_parser = subparsers.add_parser(plugin.name, help=plugin.description)
    plugin.register_args(plugin_parser)  # Plugin builds its subcommands
```

### 4. Argument Registration

`register_args()` creates subparsers for each command and adds arguments 
from config schemas:

```python
def register_args(self, parser: argparse.ArgumentParser) -> None:
    # Global config file option
    parser.add_argument("-c", "--config", type=Path)
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    for cmd_name, cmd_def in self._commands.items():
        sub = subparsers.add_parser(cmd_name, help=cmd_def.help)
        self._add_config_args(sub, cmd_def.config_class)
```

Arguments are grouped by config class hierarchy for clean help output.

### 5. Command Dispatch

When invoked, `run()` loads configuration and dispatches to the command method:

```python
async def run(self, cli_args: argparse.Namespace) -> None:
    command_name = cli_args.command
    cmd_def = self._commands[command_name]
    
    # Load and merge config from CLI, YAML, ENV
    config = self.load_config(cli_args, cmd_def.config_class, command_name)
    
    # Call the decorated method
    method = getattr(self, cmd_def.method_name)
    await method(config)
```
