"""
CLI Entry Point.

Main command-line interface for the crawler framework.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import argparse
import asyncio
import sys

from crawlers.core import output
from crawlers.plugins import REGISTERED_PLUGINS


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
        output.info("Available plugins:")
        for p in REGISTERED_PLUGINS:
            print(f"  {p.name:<10} - {p.description}")
        return 0

    if not args.plugin:
        parser.print_help()
        return 1

    # Find plugin
    plugin = plugin_instances.get(args.plugin)
    if not plugin:
        output.error(f"Plugin '{args.plugin}' not found.")
        return 1

    try:
        # Plugin handles everything: config loading, command dispatch
        asyncio.run(plugin.run(args))
        return 0

    except ValueError as e:
        output.error(str(e))
        return 1

    except Exception as e:
        output.error(f"Execution failed: {e}")
        if output.get_level() <= output.LogLevel.DEBUG:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
