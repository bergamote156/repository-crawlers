"""
Registrar CLI

Command-line interface for dataset registration in Onedata.
"""

# pylint: disable=duplicate-code

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import sys
from pathlib import Path

import click
import yaml

from registrar import __version__, output
from registrar.api import OnepanelClient
from registrar.cache import ResourceCache
from registrar.config import config_to_dict, load_config
from registrar.operations import load_cache
from registrar.registrar import DatasetRegistrar


@click.group()
@click.version_option(version=__version__, prog_name="registrar")
@click.option(
    "--config",
    "-c",
    "config_file",
    type=click.Path(exists=True, path_type=Path),
    help="Path to configuration file (YAML)",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    default=False,
    help="Suppress progress messages (only warnings, errors and summary)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Show detailed debug output",
)
@click.pass_context
def cli(ctx: click.Context, config_file: Path | None, quiet: bool, verbose: bool):
    """Dataset Registrar - Register datasets in Onedata."""
    ctx.ensure_object(dict)
    ctx.obj["config_file"] = config_file

    # Determine log level from flags (verbose takes precedence)
    if verbose:
        ctx.obj["log_level"] = "debug"
    elif quiet:
        ctx.obj["log_level"] = "warning"
    else:
        ctx.obj["log_level"] = None  # Use config/env default


@cli.command()
@click.argument("datasets_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--limit",
    "-n",
    type=int,
    default=None,
    help="Maximum number of datasets to process (default: all)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Validate datasets without registering",
)
@click.pass_context
def register(
    ctx: click.Context,
    datasets_file: Path,
    limit: int | None,
    dry_run: bool,
):
    """
    Register datasets from JSON file into Onedata.

    DATASETS_FILE is a JSON file containing an array of datasets to register.
    """
    # Build CLI overrides
    cli_overrides: dict = {}

    # Apply log level from CLI flags
    if log_level := ctx.obj.get("log_level"):
        cli_overrides.setdefault("logging", {})["level"] = log_level

    config = load_config(
        config_file=ctx.obj.get("config_file"),
        cli_overrides=cli_overrides if cli_overrides else None,
    )

    # Initialize output module with configured level
    output.set_level(config.logging.level)

    # Validate tokens
    if not dry_run:
        if not config.tokens.admin_token:
            output.error("REGISTRAR_ADMIN_TOKEN is not set!")
            sys.exit(1)
        if not config.tokens.space_owner_token:
            output.error("REGISTRAR_SPACE_OWNER_TOKEN is not set!")
            sys.exit(1)

    # Run registration
    registrar = DatasetRegistrar(config)

    try:
        summary = registrar.run(
            datasets_file=datasets_file,
            limit=limit,
            dry_run=dry_run,
        )

        # Exit with error code if any failures
        if summary.failed > 0:
            sys.exit(1)

    except KeyboardInterrupt:
        output.warning("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:  # pylint: disable=broad-exception-caught
        output.error(f"Fatal error: {e}")
        sys.exit(1)


@cli.command("list-spaces")
@click.pass_context
def list_spaces(ctx: click.Context):
    """List HTTP readonly spaces on the provider."""
    cli_overrides: dict = {}
    if log_level := ctx.obj.get("log_level"):
        cli_overrides.setdefault("logging", {})["level"] = log_level

    config = load_config(
        config_file=ctx.obj.get("config_file"),
        cli_overrides=cli_overrides if cli_overrides else None,
    )
    output.set_level(config.logging.level)

    if not config.tokens.admin_token:
        output.error("REGISTRAR_ADMIN_TOKEN is not set!")
        sys.exit(1)

    onepanel = OnepanelClient(
        domain=config.onedata.oneprovider_domain,
        token=config.tokens.admin_token,
        port=config.onedata.panel_port,
        verify_ssl=config.onedata.verify_ssl,
    )

    cache = ResourceCache()
    load_cache(onepanel=onepanel, cache=cache)

    output.always(f"\nHTTP readonly spaces ({len(cache.spaces)}):\n")
    output.always(f"{'Name':<40} {'Space ID':<40} {'Storage ID'}")
    output.always("-" * 100)

    for name, space_info in sorted(cache.spaces.items()):
        output.always(f"{name:<40} {space_info['id']:<40} {space_info['storage_id']}")


@cli.command("list-storages")
@click.pass_context
def list_storages(ctx: click.Context):
    """List HTTP readonly storages on the provider."""
    cli_overrides: dict = {}
    if log_level := ctx.obj.get("log_level"):
        cli_overrides.setdefault("logging", {})["level"] = log_level

    config = load_config(
        config_file=ctx.obj.get("config_file"),
        cli_overrides=cli_overrides if cli_overrides else None,
    )
    output.set_level(config.logging.level)

    if not config.tokens.admin_token:
        output.error("REGISTRAR_ADMIN_TOKEN is not set!")
        sys.exit(1)

    onepanel = OnepanelClient(
        domain=config.onedata.oneprovider_domain,
        token=config.tokens.admin_token,
        port=config.onedata.panel_port,
        verify_ssl=config.onedata.verify_ssl,
    )

    cache = ResourceCache()
    load_cache(onepanel=onepanel, cache=cache)

    output.always(f"\nHTTP readonly storages ({len(cache.storages)}):\n")
    output.always(f"{'Name':<40} {'Storage ID':<40} {'Endpoint'}")
    output.always("-" * 100)

    for name, storage_info in sorted(cache.storages.items()):
        endpoint = storage_info.get("details", {}).get("endpoint", "")
        output.always(f"{name:<40} {storage_info['id']:<40} {endpoint}")


@cli.command("show-config")
@click.pass_context
def show_config(ctx: click.Context):
    """Show current configuration."""
    config = load_config(config_file=ctx.obj.get("config_file"))
    config_dict = config_to_dict(config)

    output.always("Current configuration:\n")
    output.always(yaml.dump(config_dict, default_flow_style=False, sort_keys=False))


def main():
    """Main entry point."""
    cli()  # pylint: disable=no-value-for-parameter


if __name__ == "__main__":
    main()
