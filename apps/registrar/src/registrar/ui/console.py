"""Singleton rich Console for the registrar CLI."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from rich.console import Console

from registrar.ui.theme import THEME

_console: Console | None = None


def get_console() -> Console:
    """Return the process-wide Console instance (created on first call)."""
    global _console  # noqa: PLW0603
    if _console is None:
        _console = Console(theme=THEME)
    return _console
