"""
CLI Entry Point.

Top-level dispatcher.  Splits `argv` into `[global flags] [plugin]
[plugin args]`, handles a few global flags itself (`--version`,
`--list-plugins`, `-v` / `-q`), and forwards the plugin's argv slice
to its `CommandApp` (`plugin.run(...)`).  Each plugin owns its own
argparse tree via `confline.CommandApp`; this module is intentionally
thin.

The split is done by hand (first non-flag argv is the plugin name)
rather than via argparse, because argparse's `--help` action would
otherwise eat `crawlers <plugin> --help` at the top level instead of
forwarding it.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import argparse
import difflib
import sys
import traceback
from collections.abc import Sequence

from rich.table import Table

from crawlers.plugins import REGISTERED_PLUGINS
from crawlers.ui import console

_VERSION = "1.0.0"
_EXIT_USAGE = 64
_EXIT_INTERRUPTED = 130
_DID_YOU_MEAN_CUTOFF = 0.6
_DID_YOU_MEAN_LIMIT = 3


def main() -> int:  # noqa: PLR0911 — each return is a distinct exit-code path
    """Top-level CLI entry point — dispatch to the selected plugin."""
    plugins_by_name = {p.name: p for p in REGISTERED_PLUGINS}
    argv = sys.argv[1:]

    global_argv, plugin_name, plugin_argv = _split_argv(argv)

    parser = _build_top_parser(plugins_by_name)
    args = parser.parse_args(global_argv if plugin_name is not None else argv)

    if args.verbose:
        console.set_verbosity(console.Verbosity.VERBOSE)
    elif args.quiet:
        console.set_verbosity(console.Verbosity.QUIET)

    if args.list_plugins:
        _print_plugins(plugins_by_name)
        return 0

    if plugin_name is None:
        parser.print_help()
        return 1

    plugin = plugins_by_name.get(plugin_name)
    if plugin is None:
        suggestions = difflib.get_close_matches(
            plugin_name,
            plugins_by_name.keys(),
            n=_DID_YOU_MEAN_LIMIT,
            cutoff=_DID_YOU_MEAN_CUTOFF,
        )
        msg = f"unknown plugin: {plugin_name!r}"
        if suggestions:
            msg += f" — did you mean {', '.join(suggestions)}?"
        console.error(msg)
        return _EXIT_USAGE

    try:
        result = plugin.run(plugin_argv)
        return result if isinstance(result, int) else 0

    except KeyboardInterrupt:
        # `run_crawl` handles its own cleanup banner; here we just translate
        # the interrupt to the conventional shell exit code.
        return _EXIT_INTERRUPTED

    except ValueError as e:
        console.error(str(e))
        return 1

    except Exception as e:
        console.error(f"Execution failed: {e}")
        traceback.print_exc()
        return 1


def _split_argv(argv: Sequence[str]) -> tuple[list[str], str | None, list[str]]:
    """Split `argv` at the first non-flag argument (the plugin name).

    Returns `(global_argv, plugin_name, plugin_argv)`. If no plugin
    name is found, `plugin_name` is `None` and the whole input goes
    into the first element.
    """
    for i, arg in enumerate(argv):
        if not arg.startswith("-"):
            return list(argv[:i]), arg, list(argv[i + 1 :])
    return list(argv), None, []


def _build_top_parser(plugins_by_name: dict) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crawlers",
        description="Public Data Crawlers Framework",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_VERSION}")
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
    parser.add_argument(
        "--list-plugins",
        action="store_true",
        help="List available plugins and exit",
    )
    # `plugin` is not a real argparse argument — it's pre-extracted by
    # `_split_argv` so `crawlers <plugin> --help` doesn't get its
    # `--help` swallowed at the top level. We add it as metadata-only
    # via the epilog so `--help` still names it.
    parser.epilog = (
        f"plugin: one of {', '.join(sorted(plugins_by_name))}\n"
        f"        anything after the plugin name is forwarded to it.\n"
        f"        e.g. `crawlers ecudo crawl --help`."
    )
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    return parser


def _print_plugins(plugins_by_name: dict) -> None:
    table = Table(title="Available Plugins", show_header=True, header_style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    for plugin in plugins_by_name.values():
        table.add_row(plugin.name, plugin.description)
    console.print(table)


if __name__ == "__main__":
    sys.exit(main())
