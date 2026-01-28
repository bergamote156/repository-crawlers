"""
Plugin Interface

Abstract base class for crawler plugins with declarative command registration.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import argparse
import os
from abc import ABC
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar

import yaml

from crawlers.core.config import ConfigSchema

ConfigT = TypeVar("ConfigT")

# --- Command Definition ---


@dataclass
class CommandDef:
    """Definition of a CLI command."""

    name: str
    help: str
    method_name: str
    config_class: type[Any] | Callable[[], type[Any]]


def command(
    name: str,
    config: type[Any] | Callable[[], type[Any]],
    *,
    help: str = "",
) -> Callable:
    """
    Decorator to register a method as a CLI command.

    Args:
        name: Command name (e.g. 'crawl', 'list-orgs')
        config: Dataclass config class for this command
        help: Help text for the command

    Example:
        @command("crawl", EcudoCrawlConfig, help="Crawl datasets")
        async def run_crawl(self, config: EcudoCrawlConfig) -> None:
            ...
    """

    def decorator(func: Callable) -> Callable:
        func._command_def = CommandDef(
            name=name,
            help=help,
            method_name=func.__name__,
            config_class=config,
        )
        return func

    return decorator


# --- Base Plugin Class ---


class CrawlerPlugin(ABC):
    """
    Abstract base class for crawler plugins.

    Plugins define commands using the @command decorator. The base class
    automatically:
    1. Collects commands from decorated methods
    2. Builds CLI argument parser from config field metadata
    3. Loads and validates configuration
    4. Dispatches to the appropriate command method

    Example:
        class MyPlugin(CrawlerPlugin):
            name = "myplugin"
            description = "My crawler plugin"

            @command("crawl", MyCrawlConfig, help="Run crawler")
            async def run_crawl(self, config: MyCrawlConfig) -> None:
                ...
    """

    name: str
    description: str

    # Populated by __init_subclass__
    _commands: dict[str, CommandDef]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Collect @command decorated methods from the subclass."""
        super().__init_subclass__(**kwargs)
        cls._commands = {}

        for attr_name in dir(cls):
            if attr_name.startswith("_"):
                continue

            method = getattr(cls, attr_name, None)
            if callable(method) and hasattr(method, "_command_def"):
                cmd_def: CommandDef = method._command_def
                cls._commands[cmd_def.name] = cmd_def

    def register_args(self, parser: argparse.ArgumentParser) -> None:
        """
        Build subparsers from @command decorated methods and their config metadata.

        This is called by the CLI framework to set up argument parsing.
        Plugins typically don't need to override this method.
        """
        # Global config file option
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
        self, parser: argparse.ArgumentParser, config_cls: type[Any]
    ) -> None:
        """Add CLI arguments from config schema with argument groups."""
        schema: ConfigSchema = config_cls.__config_schema__

        for group in schema.groups:
            arg_group = parser.add_argument_group(
                title=group.name,
                description=group.description,
            )

            for field_info in group.fields:
                # Skip nested configs (YAML only) and CLI-disabled fields
                if field_info.nested_schema or field_info.cli is None:
                    continue

                cli = field_info.cli
                if cli.is_positional:
                    arg_group.add_argument(cli.names[0], **cli.kwargs)
                else:
                    arg_group.add_argument(*cli.names, **cli.kwargs)

    async def run(self, cli_args: argparse.Namespace) -> None:
        """
        Dispatch to the appropriate command method.

        Args:
            cli_args: Parsed CLI arguments including 'command' attribute
        """
        command_name = getattr(cli_args, "command", None)
        if not command_name:
            raise ValueError("No command specified")

        if command_name not in self._commands:
            raise ValueError(f"Unknown command: {command_name}")

        cmd_def = self._commands[command_name]
        config = self.load_config(cli_args, cmd_def.config_class, command_name)

        method = getattr(self, cmd_def.method_name)
        await method(config)

    def load_config(
        self,
        cli_args: argparse.Namespace,
        config_cls: type[ConfigT],
        command_name: str,
    ) -> ConfigT:
        """
        Build and validate configuration from ENV + YAML + CLI.

        Priority:
        1. CLI arguments
        2. Command-specific YAML (plugins.<plugin>.commands.<cmd>.<key>)
        3. Plugin-level YAML (plugins.<plugin>.<key>)
        4. Global YAML (global.<key>)
        5. Environment variables
        6. Default values

        Args:
            cli_args: Parsed CLI arguments
            config_cls: Dataclass config to instantiate
            command_name: Name of the command being executed

        Returns:
            Validated configuration object
        """
        # Load YAML if provided
        yaml_data: dict[str, Any] = {}
        if config_path := getattr(cli_args, "config", None):
            if config_path and config_path.exists():
                yaml_data = yaml.safe_load(config_path.read_text()) or {}

        global_yaml = yaml_data.get("global", {})
        plugin_yaml = yaml_data.get("plugins", {}).get(self.name, {})

        # Support hierarchical config: plugins.<name>.commands.<cmd>
        command_yaml = plugin_yaml.get("commands", {}).get(command_name, {})

        # Instantiate dataclass recursively
        return self._instantiate_config(
            config_cls, global_yaml, plugin_yaml, command_yaml, cli_args
        )

    def _instantiate_config(
        self,
        config_cls: type[ConfigT],
        global_yaml: dict[str, Any],
        plugin_yaml: dict[str, Any],
        command_yaml: dict[str, Any],
        cli_args: argparse.Namespace | None,
    ) -> ConfigT:
        """Recursively instantiate dataclass config from sources using schema."""
        schema: ConfigSchema = config_cls.__config_schema__
        init_kwargs: dict[str, Any] = {}

        for field_info in schema.all_fields():
            field_name = field_info.name

            # Handle nested dataclass configs
            if field_info.nested_schema:
                if field_info.yaml_key:
                    yaml_key = field_info.yaml_key

                    global_field_section = get_yaml_section(global_yaml, yaml_key)
                    plugin_field_section = get_yaml_section(plugin_yaml, yaml_key)
                    command_field_section = get_yaml_section(command_yaml, yaml_key)
                else:
                    global_field_section = {}
                    plugin_field_section = {}
                    command_field_section = {}

                nested_obj = self._instantiate_config(
                    field_info.nested_schema.config_class,
                    global_field_section,
                    plugin_field_section,
                    command_field_section,
                    None,  # No CLI args for nested configs
                )
                init_kwargs[field_name] = nested_obj
                continue

            # Resolve value from sources (CLI > YAML > ENV)
            value = self._resolve_value(
                field_info, global_yaml, plugin_yaml, command_yaml, cli_args
            )

            if value is not None:
                init_kwargs[field_name] = self._coerce_type(value, field_info)

        return config_cls(**init_kwargs)

    def _resolve_value(
        self,
        field_info: Any,  # ConfigFieldInfo
        global_yaml: dict[str, Any],
        plugin_yaml: dict[str, Any],
        command_yaml: dict[str, Any],
        cli_args: argparse.Namespace | None,
    ) -> Any:
        """Resolve config value based on priority using field info."""
        # 1. CLI (Highest priority)
        if cli_args and field_info.cli:
            val = getattr(cli_args, field_info.cli.attr_name, None)
            if val is not None:
                return val

        # 2. Command YAML
        yaml_key = field_info.yaml_key
        if yaml_key and yaml_key in command_yaml:
            return command_yaml[yaml_key]

        # 3. Plugin YAML
        if yaml_key and yaml_key in plugin_yaml:
            return plugin_yaml[yaml_key]

        # 4. Global YAML
        if yaml_key and yaml_key in global_yaml:
            return global_yaml[yaml_key]

        # 5. Environment variable
        if field_info.env_var:
            val = os.environ.get(field_info.env_var)
            if val is not None:
                return val

        return None

    def _coerce_type(self, value: Any, field_info: Any) -> Any:
        """Type coercion using pre-computed field_type."""
        if value is None:
            return None

        target_type = field_info.field_type

        if target_type is bool:
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes", "on")
            return bool(value)

        if target_type is int:
            return int(value)

        if target_type is float:
            return float(value)

        if target_type is str:
            return str(value)

        # Fallback: return value as-is
        return value


def get_yaml_section(config_yaml, key):
    """Safely get a section from YAML dict."""
    if isinstance(config_yaml, dict):
        return config_yaml.get(key, {})

    return {}
