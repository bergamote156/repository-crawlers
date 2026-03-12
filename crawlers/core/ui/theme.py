"""
Console Theme

Color definitions and styling for the CLI interface.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from enum import IntEnum
from typing import Final

from rich.theme import Theme


# Output verbosity levels
class Verbosity(IntEnum):
    """Output verbosity levels."""

    QUIET = 0  # Errors only
    NORMAL = 1  # Standard output
    VERBOSE = 2  # Debug info


# Theme color definitions
THEME_STYLES: Final[dict[str, str]] = {
    # Message types
    "info": "cyan",
    "success": "green",
    "warning": "yellow",
    "error": "red bold",
    "debug": "dim",
    # UI elements
    "muted": "dim",
    "highlight": "bold cyan",
    "header": "bold white",
    # Processor states
    "processor.enabled": "green",
    "processor.disabled": "dim",
    # Statistics
    "stat.label": "bold",
    "stat.value": "cyan",
    "stat.good": "green",
    "stat.bad": "red",
    # Progress
    "progress.description": "cyan",
    "progress.percentage": "magenta",
}

# Create Rich Theme instance
THEME: Final[Theme] = Theme(THEME_STYLES)
