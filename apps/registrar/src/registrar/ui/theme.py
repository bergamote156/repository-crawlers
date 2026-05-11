"""Registrar CLI theme — color palette and style keys for rich output."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from typing import Final

from rich.theme import Theme

THEME_STYLES: Final[dict[str, str]] = {
    "success": "green",
    "warning": "dark_orange",
    "danger": "red",
    "info": "cyan",
    "muted": "grey50",
    "code": "bold cyan",
}

THEME: Final[Theme] = Theme(THEME_STYLES)
