"""Logging setup for registrar commands."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import logging
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler


def setup_logging(
    *,
    console: Console,
    level: str = "INFO",
    run_dir: Path | None = None,
) -> None:
    """Configure stdlib logging for a registrar command.

    For `register`: pass `run_dir` to get a FileHandler writing the full
    DEBUG stream to `registration.log` inside the run directory.

    For `list-*` commands: omit `run_dir` — console-only logging.
    """
    root = logging.getLogger("registrar")
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    rich_handler = RichHandler(
        console=console,
        show_path=False,
        show_time=False,
        markup=True,
    )
    rich_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(rich_handler)

    if run_dir is not None:
        file_handler = logging.FileHandler(run_dir / "registration.log")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
        )
        root.addHandler(file_handler)
