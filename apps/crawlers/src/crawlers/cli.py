"""
CLI Entry Point.

Main command-line interface for the crawler framework.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import argparse
import asyncio
import sys
import traceback

from rich.table import Table

from crawlers.plugins import REGISTERED_PLUGINS
from crawlers.ui import console


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="crawlers",
        description="Public Data Crawlers Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0",
    )
    parser.add_argument(
        "--list-plugins",
        action="store_true",
        help="List available plugins and exit",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output (debug messages)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress non-error output",
    )

    # Subparsers for plugins
    subparsers = parser.add_subparsers(
        dest="plugin",
        help="Plugin to use",
        metavar="PLUGIN",
    )

    # Create plugin instances and register their parsers
    plugin_instances = {p.name: p for p in REGISTERED_PLUGINS}

    for plugin in REGISTERED_PLUGINS:
        plugin_parser = subparsers.add_parser(
            plugin.name,
            help=plugin.description,
            description=plugin.description,
        )
        plugin.register_args(plugin_parser)

    # Parse args
    args = parser.parse_args()

    # Handle basic commands
    if args.list_plugins:
        table = Table(title="Available Plugins", show_header=True, header_style="bold")
        table.add_column("Name", style="cyan")
        table.add_column("Description")
        for p in REGISTERED_PLUGINS:
            table.add_row(p.name, p.description)
        console.print(table)
        return 0

    if not args.plugin:
        parser.print_help()
        return 1

    # Find plugin
    selected_plugin = plugin_instances.get(args.plugin)
    if not selected_plugin:
        console.error(f"Plugin '{args.plugin}' not found.")
        return 1

    # Set verbosity from CLI flags
    if args.verbose:
        console.set_verbosity(console.Verbosity.VERBOSE)
    elif args.quiet:
        console.set_verbosity(console.Verbosity.QUIET)

    try:
        # Plugin handles everything: config loading, command dispatch
        asyncio.run(selected_plugin.run(args))
        return 0

    except ValueError as e:
        console.error(str(e))
        return 1

    except Exception as e:
        console.error(f"Execution failed: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
