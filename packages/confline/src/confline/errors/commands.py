"""
Command registration and dispatch errors.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from collections.abc import Sequence
from typing import ClassVar

from confline.errors.base import ConfigError


class CommandRegistrationError(ConfigError):
    """A @command decorator collides with an already-registered name or alias.

    This is a framework/configuration error raised while commands are
    collected. It normally needs no structured fields because the message
    is built at the detection site where the conflicting command names
    are known.
    """


class UnknownCommandError(ConfigError):
    """User invoked a subcommand that is not registered.

    - `given` — the token argparse rejected.
    - `available` — all registered names; feeds the "Available commands" block.
    - `suggestions` — fuzzy matches; feeds the "Did you mean" block.

    `str()` includes suggestions for non-CLI callers; `render_for_cli` expands
    all three fields.
    """

    _EXIT_CODE: ClassVar[int] = 64  # EX_USAGE

    def __init__(
        self,
        given: str | None,
        *,
        available: Sequence[str],
        suggestions: Sequence[str] = (),
    ) -> None:
        self.given = given
        self.available = tuple(available)
        self.suggestions = tuple(suggestions)

        msg = f"unknown command: {given!r}"
        if suggestions:
            msg += f" (did you mean: {', '.join(suggestions)})"

        super().__init__(msg)
