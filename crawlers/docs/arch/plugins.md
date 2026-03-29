# Plugin System

## Overview

The crawlers framework uses a plugin architecture where each data source
(Ecudo, EODC, etc.) is implemented as a plugin. Plugins define commands
using decorators, and the framework automatically handles:

- CLI argument parsing from config schemas
- Configuration loading from CLI/YAML/ENV
- Command dispatch to appropriate methods

There are two plugin base classes:

| Class | Use when                                                            |
|-------|---------------------------------------------------------------------|
| `DefaultCrawlerPlugin` | Standard crawl + optional extra commands (90% of cases)             |
| `CrawlerPlugin` | Non-stadard use case that cannot be handled by `DefaultCrawlerPlugin` |

## DefaultCrawlerPlugin

The main base class for crawler plugins. Subclass and implement `prepare_crawl()` and the
framework handles client lifecycle, pipeline construction, parallel execution,
state persistence, and display.

```python
from crawlers.core.default.plugin import DefaultCrawlerPlugin, CrawlSpec
from crawlers.core.default.config import DefaultCrawlConfig


class MyPlugin(DefaultCrawlerPlugin):
    name = "myplugin"
    description = "Crawl MyDataSource"
    config_class = MyCrawlConfig  # defaults to DefaultCrawlConfig if omitted

    def prepare_crawl(self, config: MyCrawlConfig) -> CrawlSpec:
        return CrawlSpec(
            client=MyClient(base_url=config.base_url),
            iterator_opts=MyOpts(page_size=config.page_size),
            parser=MyParser(),
            metadata_builder=MyMetadataBuilder(),
            run_context_name=config.collection,
            max_items=config.max_records,
            url_validation=config.get_url_validator_enabled(),
        )
```

**Required class attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Plugin identifier, used as CLI subcommand |
| `description` | `str` | Short description for `--help` |

**Optional class attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `config_class` | `type[DefaultCrawlConfig]` | Config class for the crawl command. Defaults to `DefaultCrawlConfig`. |

### Auto-registered crawl command

Defining `name` on a `DefaultCrawlerPlugin` subclass automatically registers
a `crawl` CLI command. No `@command` decorator needed.

### Optional hooks

```python
async def before_crawl(self, spec: CrawlSpec) -> None:
    """Called after client session opens. Use for validation."""

async def after_crawl(self) -> None:
    """Called after successful crawl completion."""
```

`before_crawl` receives the full `CrawlSpec` — use `cast()` to get a typed client:

```python
async def before_crawl(self, spec: CrawlSpec) -> None:
    client = cast(MyClient, spec.client)
    orgs = await client.list_organizations()
    if not any(o["id"] == self._config.org for o in orgs):
        console.error("Organization not found")
        sys.exit(1)
```

### Pipeline customization

The default pipeline is:
```
ParserProcessor → URLValidator → Tap(raw) → OnedataConverter → Tap(processed)
```

Override `build_pipeline()` to customize (e.g. use `DatasetFetcher` instead of
`ParserProcessor`, or add `DiversityFilter`):

```python
def build_pipeline(self, spec: CrawlSpec, ctx: DefaultRunContext) -> ProcessorPipeline:
    client = cast(MyClient, spec.client)
    return ProcessorPipeline(
        processors=[
            DatasetFetcher(fetch_fn=client.get_details, parser=spec.parser),
            URLValidator(validate_fn=client.validate_url, enabled=spec.url_validation),
            DiversityFilter(max_similar=10),
            Tap(ctx.raw_sink, transform=lambda d: d.to_json()),
            OnedataConverter(metadata_builder=spec.metadata_builder),
            Tap(ctx.processed_sink, transform=lambda d: d.to_json()),
        ],
        rejection_sink=ctx.rejection_sink,
    )
```

## CrawlerPlugin Base Class

For plugins that only need extra commands (no crawl infrastructure):

```python
from crawlers.core.abc.plugin import CrawlerPlugin, command


class MyPlugin(CrawlerPlugin):
    name = "myplugin"
    description = "My crawler"

    @command("list-items", MyApiConfig, help="List available items")
    async def list_items(self, config: MyApiConfig) -> None:
        ...
```

`DefaultCrawlerPlugin` inherits from `CrawlerPlugin`, so all `@command` features
work in both.

## @command Decorator

Registers a method as an additional CLI command:

```python
@command(
    name: str,                  # Command name (e.g. "list-orgs")
    config: type[ConfigBase],   # Config class for this command
    *,
    help: str = "",             # Help text
)
```

**Example:**

```python
@command("list-orgs", EcudoApiConfig, help="List available organizations")
async def list_organizations(self, config: EcudoApiConfig) -> None:
    async with EcudoClient(base_url=config.base_url) as client:
        orgs = await client.get_organizations()
        ...
```

**Generated CLI:** `crawlers ecudo list-orgs [OPTIONS]`

Use lazy imports inside command methods for faster CLI startup:

```python
@command("list-orgs", EcudoApiConfig, help="List available organizations")
async def list_organizations(self, config: EcudoApiConfig) -> None:
    from .api import EcudoClient  # Lazy import
    ...
```

## Plugin Lifecycle

### 1. Registration

Plugins are instantiated in `crawlers/plugins/__init__.py`:

```python
from crawlers.plugins.ecudo.plugin import EcudoPlugin
from crawlers.plugins.eodc.plugin import EODCPlugin

REGISTERED_PLUGINS = [
    EcudoPlugin(),
    EODCPlugin(),
]
```

### 2. Command Collection

When a `CrawlerPlugin` subclass is defined, `__init_subclass__` collects all
`@command`-decorated methods. For `DefaultCrawlerPlugin` subclasses, the `crawl`
command is also registered automatically.

### 3. CLI Generation

The main CLI creates subparsers for each plugin:

```python
for plugin in REGISTERED_PLUGINS:
    plugin_parser = subparsers.add_parser(plugin.name, help=plugin.description)
    plugin.register_args(plugin_parser)
```

### 4. Argument Registration

`register_args()` creates subparsers for each command and adds typed arguments
from config schemas. Arguments are grouped by config class hierarchy in help output.

### 5. Command Dispatch

`run()` loads configuration and dispatches to the command method:

```python
async def run(self, cli_args: argparse.Namespace) -> None:
    command_name = cli_args.command
    cmd_def = self._commands[command_name]
    config = self.load_config(cli_args, cmd_def.config_class, command_name)
    method = getattr(self, cmd_def.method_name)
    await method(config)
```

## Example CLI Usage

```
crawlers [OPTIONS] PLUGIN COMMAND [ARGS]

crawlers --list-plugins
crawlers -v ecudo crawl iopan -n 100 -o ./data
crawlers -c config.yaml ecudo list-orgs
crawlers eodc crawl s1-grd --datetime 2025-01-01/2025-01-31
```
