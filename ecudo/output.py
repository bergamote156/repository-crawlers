"""
eCUDO Output Helper

Centralized output handling with log levels.
Provides consistent logging interface across all modules.
"""

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


def set_level(level: LogLevel | str) -> None:
    """
    Set global log level.

    Args:
        level: LogLevel enum or string ('debug', 'info', 'warning', 'error', 'silent')
    """
    global _level  # pylint: disable=global-statement

    if isinstance(level, str):
        level = LogLevel[level.upper()]
    _level = level


def get_level() -> LogLevel:
    """Get current log level."""
    return _level


def debug(message: str) -> None:
    """Print debug message (most verbose)."""
    if _level <= LogLevel.DEBUG:
        print(message)


def info(message: str) -> None:
    """Print info message (normal verbosity)."""
    if _level <= LogLevel.INFO:
        print(message)


def warning(message: str) -> None:
    """Print warning message (reduced verbosity)."""
    if _level <= LogLevel.WARNING:
        print(message)


def error(message: str) -> None:
    """Print error message (always shown unless SILENT)."""
    if _level <= LogLevel.ERROR:
        print(message)


def always(message: str) -> None:
    """Print message regardless of log level (for summaries)."""
    print(message)


# Convenience aliases matching current emoji conventions
def progress(message: str) -> None:
    """Print progress info (📄, 📦, 🚀, 📡)."""
    info(message)


def success(message: str) -> None:
    """Print success message (✅)."""
    info(message)


def stats(message: str) -> None:
    """Print statistics (📊, 📝)."""
    info(message)
