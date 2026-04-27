"""Crawler plugin base class."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import argparse
import asyncio
import inspect
import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack
from dataclasses import asdict, dataclass
from pathlib import Path
from pprint import pformat
from typing import Any, get_type_hints

import yaml
from rich.panel import Panel
from rich.table import Table

from crawlers.core.config import ConfigBase
from crawlers.core.crawl_config import CrawlConfig
from crawlers.core.result import Result
from crawlers.core.runner import CrawlStats, run_parallel_crawl
from crawlers.core.workspace import RunContext, make_run_dir
from crawlers.model.dataset import OnedataDataset
from crawlers.ui import console

# ─────────────────────────────────────────────────────────────────────────────
# Command definition & decorator
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CommandDef:
    """Definition of a CLI command."""

    name: str
    help: str
    method_name: str
    config_class: type[ConfigBase]


def command(
    fn: Callable | None = None,
    /,
    *,
    name: str | None = None,
    config: type[ConfigBase] | None = None,
    help: str | None = None,
) -> Callable:
    """
    Register a method as a CLI command.

    Can be used bare (`@command`) or with keyword arguments
    (`@command(name="list-orgs")`).  Anything not supplied is inferred:
    name from the method name, config from the first `ConfigBase`-typed
    parameter, help from the docstring.

    Example:

        @command
        async def list_orgs(self, config: EcudoApiConfig, stack: AsyncExitStack) -> None:
            \"\"\"List available organizations.\"\"\"
            ...
    """

    def decorator(func: Callable) -> Callable:
        cmd_name = name if name is not None else _infer_name(func)
        cmd_config = config if config is not None else _infer_config_class(func)
        cmd_help = help if help is not None else _infer_help(func)

        func._command_def = CommandDef(  # type: ignore[attr-defined]
            name=cmd_name, help=cmd_help, method_name=func.__name__, config_class=cmd_config
        )
        return func

    if fn is not None:
        return decorator(fn)
    return decorator


def _infer_name(method: Callable) -> str:
    """Derive command name from method name (underscores → hyphens)."""
    return method.__name__.replace("_", "-")


def _infer_config_class(method: Callable) -> type[ConfigBase]:
    """Extract the config type from the first annotated parameter after *self*."""
    hints = get_type_hints(method)
    params = list(inspect.signature(method).parameters.values())

    for param in params[1:]:  # skip self
        hint = hints.get(param.name)
        if hint is None:
            continue
        if isinstance(hint, type) and issubclass(hint, ConfigBase):
            return hint

    raise TypeError(
        f"Cannot infer config class for {method.__qualname__}: "
        f"no parameter annotated with a ConfigBase subclass"
    )


def _infer_help(method: Callable) -> str:
    """Use first line of docstring as help text."""
    doc = inspect.getdoc(method)
    if doc:
        return doc.split("\n", 1)[0].rstrip(".")
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Plugin base class
# ─────────────────────────────────────────────────────────────────────────────


class CrawlerPlugin[RawT, ConfigT: CrawlConfig](ABC):
    """
    Base class for crawler plugins.

    Combines the command system (`@command`, argparse, multi-source config
    loading CLI > YAML > ENV > defaults) with the crawl lifecycle (`setup`
    → `iterate_datasets` → `process`, parallel workers, JSONL sink).

    The `crawl` command is auto-registered on concrete subclasses that set
    `name`; extra commands use `@command`.

    Not reentrant: lifecycle hooks store mutable state on `self` (HTTP
    clients, API facades, etc.). Plugin instances in `REGISTERED_PLUGINS`
    are singletons — two concurrent crawls on the same instance would
    overwrite that state.
    """

    name: str
    description: str
    config_class: type[ConfigT] = CrawlConfig  # type: ignore[assignment]

    # Populated by __init_subclass__
    _commands: dict[str, CommandDef]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._commands = {}

        # Collect @command decorated methods
        for attr_name in dir(cls):
            if attr_name.startswith("_"):
                continue
            method = getattr(cls, attr_name, None)
            if callable(method) and hasattr(method, "_command_def"):
                cmd_def: CommandDef = method._command_def
                cls._commands[cmd_def.name] = cmd_def

        # Auto-register the `crawl` command on concrete subclasses
        if isinstance(cls.__dict__.get("name"), str) and "crawl" not in cls._commands:
            config_cls = cls.__dict__.get("config_class", cls.config_class)
            cls._commands["crawl"] = CommandDef(
                name="crawl",
                help="Crawl datasets",
                method_name="run_crawl",
                config_class=config_cls,
            )

    # --- CLI integration ---

    def register_args(self, parser: argparse.ArgumentParser) -> None:
        """Build argparse subparsers from registered commands."""
        parser.add_argument(
            "-c",
            "--config",
            type=Path,
            help="Path to YAML configuration file",
        )

        if not self._commands:
            raise ValueError("No commands defined")

        subparsers = parser.add_subparsers(
            dest="command",
            required=True,
            help="Command to execute",
            metavar="COMMAND",
        )

        for cmd_name, cmd_def in self._commands.items():
            sub = subparsers.add_parser(cmd_name, help=cmd_def.help)
            self._add_config_args(sub, cmd_def.config_class)

    def _add_config_args(
        self, parser: argparse.ArgumentParser, config_cls: type[ConfigBase]
    ) -> None:
        """Add CLI arguments from config schema with argument groups."""
        schema = config_cls.__config_schema__

        for group in schema.groups:
            arg_group = parser.add_argument_group(
                title=group.name,
                description=group.description,
            )
            for field_info in group.fields:
                if field_info.nested_schema or field_info.cli is None:
                    continue
                cli = field_info.cli
                if cli.is_positional:
                    arg_group.add_argument(cli.names[0], **cli.kwargs)
                else:
                    arg_group.add_argument(*cli.names, **cli.kwargs)

    # --- Dispatcher ---

    async def run(self, cli_args: argparse.Namespace) -> None:
        """Dispatch to the appropriate command method."""
        command_name = getattr(cli_args, "command", None)
        if not command_name:
            raise ValueError("No command specified")
        if command_name not in self._commands:
            raise ValueError(f"Unknown command: {command_name}")

        cmd_def = self._commands[command_name]
        config = self._load_config(cli_args, cmd_def.config_class, command_name)

        method = getattr(self, cmd_def.method_name)
        async with AsyncExitStack() as stack:
            await method(config, stack)

    # --- Crawl lifecycle ---

    async def setup(self, ctx: RunContext[ConfigT], stack: AsyncExitStack) -> None:
        """
        Open plugin resources (HTTP clients, credentials).

        Store them on `self` and register async context managers on
        `stack` so they are closed automatically when the crawl ends.
        """
        return None

    async def before_crawl(self, ctx: RunContext[ConfigT]) -> None:
        """Run once after `setup` and before the worker pool starts."""
        return None

    async def after_crawl(self, ctx: RunContext[ConfigT]) -> None:
        """Run once after the worker pool finishes successfully."""
        return None

    @abstractmethod
    async def iterate_datasets(self, ctx: RunContext[ConfigT]) -> AsyncIterator[RawT]:
        """Async-iterate raw items from the upstream API."""
        raise NotImplementedError
        yield  # pragma: no cover

    @abstractmethod
    async def process(self, raw: RawT, /) -> Result[OnedataDataset, Any] | None:
        """
        Convert a raw item into an `OnedataDataset`.

        Returns:
            - `Ok(dataset)`: persisted to `processed.jsonl`
            - `Err(failure)`: persisted to `rejected.jsonl`
            - `None`: silently skipped
        """
        raise NotImplementedError

    def run_context_name(self, _config: ConfigT) -> str:
        """Short identifier appended to the run directory name."""
        return "default"

    # --- Crawl execution ---

    async def run_crawl(self, config: ConfigT, stack: AsyncExitStack) -> None:
        """Execute the `crawl` command."""
        ctx = self._create_run_context(config)
        await ctx.open(
            config_snapshot={
                "plugin": self.name,
                "config": asdict(config),  # type: ignore[call-overload]
            }
        )

        state: dict[str, Any] = {"status": "pending", "stats": CrawlStats()}

        async def finalize() -> None:
            await ctx.close(state["status"])
            self._print_summary(state["status"], state["stats"], ctx)

        stack.push_async_callback(finalize)
        self._print_banner(ctx)

        try:
            await self.setup(ctx, stack)
            await self.before_crawl(ctx)

            stats = await run_parallel_crawl(
                source_iterator=self.iterate_datasets(ctx),
                parse_fn=self.process,
                processed_sink=ctx.processed_sink,
                rejection_sink=ctx.rejection_sink,
                concurrency=config.concurrency,
                queue_size=config.queue_size,
                max_items=config.max_records,
                state_callback=lambda s: ctx.save_stats(asdict(s)),
            )
            state["stats"] = stats
            await ctx.save_stats(asdict(stats))

            await self.after_crawl(ctx)
            state["status"] = "completed"

        except (KeyboardInterrupt, asyncio.CancelledError):
            state["status"] = "interrupted"
            console.warning("Interrupted by user (Ctrl+C)")

        except Exception:
            state["status"] = "failed"
            raise

    # --- Config loading ---

    def _load_config(
        self,
        cli_args: argparse.Namespace,
        config_cls: type[ConfigBase],
        command_name: str,
    ) -> ConfigBase:
        """Build and validate configuration from ENV + YAML + CLI."""
        yaml_data: dict[str, Any] = {}
        if (config_path := getattr(cli_args, "config", None)) and config_path.exists():
            yaml_data = yaml.safe_load(config_path.read_text()) or {}

        global_yaml = yaml_data.get("global", {})
        plugin_yaml = yaml_data.get("plugins", {}).get(self.name, {})
        command_yaml = plugin_yaml.get("commands", {}).get(command_name, {})

        return self._instantiate_config(
            config_cls, global_yaml, plugin_yaml, command_yaml, cli_args
        )

    def _instantiate_config(
        self,
        config_cls: type[ConfigBase],
        global_yaml: dict[str, Any],
        plugin_yaml: dict[str, Any],
        command_yaml: dict[str, Any],
        cli_args: argparse.Namespace | None,
    ) -> ConfigBase:
        """Recursively instantiate dataclass config from sources."""
        schema = config_cls.__config_schema__
        init_kwargs: dict[str, Any] = {}

        for field_info in schema.all_fields():
            field_name = field_info.name

            if field_info.nested_schema:
                yaml_key = field_info.yaml_key
                if yaml_key:
                    g = _yaml_section(global_yaml, yaml_key)
                    p = _yaml_section(plugin_yaml, yaml_key)
                    c = _yaml_section(command_yaml, yaml_key)
                else:
                    g = p = c = {}

                init_kwargs[field_name] = self._instantiate_config(
                    field_info.nested_schema.config_class,
                    g,
                    p,
                    c,
                    None,
                )
                continue

            value = self._resolve_value(
                field_info, global_yaml, plugin_yaml, command_yaml, cli_args
            )
            if value is not None:
                init_kwargs[field_name] = _coerce(value, field_info.field_type)

        return config_cls(**init_kwargs)

    @staticmethod
    def _resolve_value(
        field_info: Any,
        global_yaml: dict[str, Any],
        plugin_yaml: dict[str, Any],
        command_yaml: dict[str, Any],
        cli_args: argparse.Namespace | None,
    ) -> Any:
        """Resolve config value: CLI > command YAML > plugin YAML > global YAML > ENV."""
        if cli_args and field_info.cli:
            val = getattr(cli_args, field_info.cli.attr_name, None)
            if val is not None:
                return val

        yaml_key = field_info.yaml_key
        for source in (command_yaml, plugin_yaml, global_yaml):
            if yaml_key and yaml_key in source:
                return source[yaml_key]

        if field_info.env_var:
            val = os.environ.get(field_info.env_var)
            if val is not None:
                return val

        return None

    # --- Internals ---

    def _create_run_context(self, config: ConfigT) -> RunContext[ConfigT]:
        run_dir = make_run_dir(
            workspace=Path(config.output_dir),
            plugin=self.name,
            context=self.run_context_name(config),
        )
        return RunContext(run_dir=run_dir, config=config)

    # --- Display ---

    def _print_banner(self, ctx: RunContext[ConfigT]) -> None:
        title = type(self).__name__
        subtitle = self.run_context_name(ctx.config)
        content = f"[header]{title}[/]\n[muted]{subtitle}[/]\n[muted]Run: {ctx.run_dir}[/]"
        console.print(Panel(content, expand=False, border_style="cyan"))
        console.newline()
        console.debug(pformat(ctx.config))

    def _print_summary(self, status: str, stats: CrawlStats, ctx: RunContext[ConfigT]) -> None:
        setup_failed = status == "failed" and stats.queued == 0

        console.newline()
        if status == "interrupted":
            console.print(Panel("[warning]:warning: Crawl Interrupted[/]", border_style="yellow"))
        elif status == "failed":
            console.print(Panel("[error]:cross_mark: Crawl Failed[/]", border_style="red"))
        else:
            console.print(
                Panel(
                    "[success]:white_check_mark: Crawl Complete[/]",
                    border_style="green",
                )
            )

        if not setup_failed:
            console.section("Crawl Statistics")
            stats_table = Table(show_header=True, header_style="bold")
            stats_table.add_column("Metric", style="cyan")
            stats_table.add_column("Count", justify="right")
            stats_table.add_row("Queued", str(stats.queued))
            stats_table.add_row("Processed", str(stats.processed))
            stats_table.add_row("Rejected", str(stats.rejected))
            stats_table.add_row("Skipped", str(stats.skipped))
            stats_table.add_row("Failed", str(stats.failed))
            console.print(stats_table)

            console.section("Output Files")
            for sink in (ctx.processed_sink, ctx.rejection_sink):
                for path in sink.artifacts():
                    console.print(f"  [muted]>[/] {path}")

        console.section("Run Directory")
        console.print(f"  {ctx.run_dir}")

        next_steps = _build_next_steps(status, stats, ctx)
        if next_steps:
            console.section("Next Steps")
            for i, step in enumerate(next_steps, 1):
                console.print(f"  {i}. {step}")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers (module-private)
# ─────────────────────────────────────────────────────────────────────────────


def _yaml_section(config_yaml: Any, key: str) -> dict:
    """Safely get a section from YAML dict."""
    if isinstance(config_yaml, dict):
        return config_yaml.get(key, {})
    return {}


def _coerce(value: Any, target_type: type) -> Any:
    """Coerce a raw config value to the target type."""
    if value is None:
        return None
    if target_type is bool:
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        return bool(value)
    if target_type in (int, float, str):
        return target_type(value)
    return value


def _build_next_steps(status: str, stats: CrawlStats, ctx: RunContext[Any]) -> list[str]:
    """Produce next-step suggestions tailored to the run outcome."""
    steps: list[str] = []

    if status == "failed":
        steps.append("Fix the error shown above and re-run the crawl")
    elif status == "interrupted":
        steps.append("Re-run the command to continue from a fresh run directory")

    if stats.processed > 0:
        steps.append("Run: registrar")

    if stats.rejected > 0:
        rejection_artifacts = ctx.rejection_sink.artifacts()
        target = rejection_artifacts[0] if rejection_artifacts else "rejected.jsonl"
        steps.append(f"Review rejected records in {target}")

    if stats.failed > 0:
        steps.append("Investigate worker failures (parser bug — see warnings above)")

    return steps
