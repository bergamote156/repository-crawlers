"""
Console Interface

Professional CLI output using Rich library.
Provides consistent, beautiful terminal output across all commands.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from contextlib import contextmanager
from typing import Any, Generator

from rich.console import Console as RichConsole
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.rule import Rule
from rich.status import Status

from crawlers.core.ui.theme import THEME, Verbosity

# ─────────────────────────────────────────────────────────────────────────────
# Console State (thin class)
# ─────────────────────────────────────────────────────────────────────────────


# pylint: disable=too-few-public-methods
class Console:
    """
    Thin wrapper holding console state.

    Use module functions as the primary API.
    """

    def __init__(self, verbosity: Verbosity = Verbosity.NORMAL):
        """Initialize console state."""
        self.verbosity = verbosity
        self.rich = RichConsole(theme=THEME)


# ─────────────────────────────────────────────────────────────────────────────
# Global Console Instance (singleton)
# ─────────────────────────────────────────────────────────────────────────────

_console: Console | None = None  # pylint: disable=invalid-name


def get_console() -> Console:
    """Get or create global console instance."""
    global _console  # pylint: disable=global-statement
    if _console is None:
        _console = Console()
    return _console


def set_verbosity(verbosity: Verbosity) -> None:
    """Set global verbosity level."""
    get_console().verbosity = verbosity


# ─────────────────────────────────────────────────────────────────────────────
# Basic Output
# ─────────────────────────────────────────────────────────────────────────────


def info(message: str) -> None:
    """Print info message (normal verbosity)."""
    c = get_console()
    if c.verbosity >= Verbosity.NORMAL:
        c.rich.print(f"[info]:information:[/] {message}")


def success(message: str) -> None:
    """Print success message (normal verbosity)."""
    c = get_console()
    if c.verbosity >= Verbosity.NORMAL:
        c.rich.print(f"[success]:white_check_mark:[/] {message}")


def warning(message: str) -> None:
    """Print warning message (always shown unless QUIET)."""
    c = get_console()
    if c.verbosity >= Verbosity.QUIET:
        c.rich.print(f"[warning]:warning:[/] {message}")


def error(message: str) -> None:
    """Print error message (always shown)."""
    c = get_console()
    c.rich.print(f"[error]:cross_mark:[/] {message}")


def debug(message: str) -> None:
    """Print debug message (verbose only)."""
    c = get_console()
    if c.verbosity >= Verbosity.VERBOSE:
        c.rich.print(f"[debug]DEBUG: {message}[/]")


def print(*args: Any, **kwargs: Any) -> None:  # pylint: disable=redefined-builtin
    """Pass-through to rich console (respects verbosity)."""
    c = get_console()
    if c.verbosity >= Verbosity.NORMAL:
        c.rich.print(*args, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Spacing & Headers
# ─────────────────────────────────────────────────────────────────────────────


def newline(count: int = 1) -> None:
    """Print empty lines for spacing."""
    c = get_console()
    for _ in range(count):
        c.rich.print()


def section(title: str) -> None:
    """Print section header with horizontal rule."""
    c = get_console()
    if c.verbosity >= Verbosity.NORMAL:
        c.rich.print()
        c.rich.print(Rule(title, style="cyan"))


# ─────────────────────────────────────────────────────────────────────────────
# Progress & Status
# ─────────────────────────────────────────────────────────────────────────────


@contextmanager
def status(message: str) -> Generator[Status, None, None]:
    """
    Context manager for spinner status.

    Usage:
        with console.status("Validating..."):
            await validate()
    """
    c = get_console()
    with c.rich.status(f"[info]{message}[/]") as status_ctx:
        yield status_ctx


def create_progress(total: int | None = None) -> Progress:
    """
    Create progress bar for crawling.

    Args:
        total: Total items if known (enables progress bar), None for spinner

    Returns:
        Progress context manager. Use with `progress.add_task()`.
    """
    c = get_console()

    if total is not None:
        # Known total: show progress bar
        columns = [
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
        ]
    else:
        # Unknown total: show spinner with count
        columns = [
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TextColumn("[progress.percentage]{task.completed} items"),
            TimeElapsedColumn(),
        ]

    return Progress(*columns, console=c.rich)
