"""
Registrar Output Helper

Centralized output handling with log levels.
Provides consistent logging interface across all modules.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import os
from enum import IntEnum


class LogLevel(IntEnum):
    """Log levels in order of verbosity."""

    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    SILENT = 100  # Suppress everything


# Global state
_level: LogLevel = LogLevel.INFO
_color_enabled = os.getenv("NO_COLOR") is None

_RESET = "\033[0m"
_COLORS = {
    LogLevel.DEBUG: "\033[36m",  # cyan
    LogLevel.INFO: "\033[34m",  # blue
    LogLevel.WARNING: "\033[33m",  # yellow
    LogLevel.ERROR: "\033[31m",  # red
}
_STATS_COLOR = "\033[35m"  # magenta
_PREFIXES = {
    LogLevel.DEBUG: "[debug]",
    LogLevel.INFO: "[info ]",
    LogLevel.WARNING: "[warn ]",
    LogLevel.ERROR: "[error]",
}


def set_level(level: LogLevel | str) -> None:
    """
    Set global log level.

    Args:
        level: LogLevel enum or string ('debug', 'info', 'warning', 'error', 'silent')
    """
    global _level  # noqa: PLW0603

    if isinstance(level, str):
        level = LogLevel[level.upper()]
    _level = level


def get_level() -> LogLevel:
    """Get current log level."""
    return _level


def debug(message: str) -> None:
    """Print debug message (most verbose)."""
    _emit(LogLevel.DEBUG, message)


def info(message: str) -> None:
    """Print info message (normal verbosity)."""
    _emit(LogLevel.INFO, message)


def warning(message: str) -> None:
    """Print warning message (reduced verbosity)."""
    _emit(LogLevel.WARNING, message)


def error(message: str) -> None:
    """Print error message (always shown unless SILENT)."""
    _emit(LogLevel.ERROR, message)


def always(message: str) -> None:
    """Print message regardless of log level (for summaries)."""
    _emit(LogLevel.INFO, message, prefix="[info ]", force=True)


def stats(message: str) -> None:
    """Print statistics."""
    _emit(LogLevel.INFO, message, prefix="[stats]", color=_STATS_COLOR)


def _emit(
    level: LogLevel,
    message: str,
    *,
    prefix: str | None = None,
    color: str | None = None,
    force: bool = False,
) -> None:
    """Emit a (potentially multi-line) message with prefix and optional color."""
    if not force and _level > level:
        return

    prefix = prefix or _PREFIXES.get(level, "[log]")
    if _color_enabled:
        color = color or _COLORS.get(level)
        if color:
            prefix = f"{color}{prefix}{_RESET}"

    lines = message.splitlines()

    # Preserve leading/trailing blank lines without a prefix
    if not lines:
        print("")
        return

    for line in lines:
        if line.strip() == "":
            print("")
        else:
            print(f"{prefix} {line}")
