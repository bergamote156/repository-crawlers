"""Rich progress bar for the registration loop.

Completed datasets scroll above the Live area (docker-pull style),
the progress panel stays pinned at the bottom.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Literal

from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.padding import Padding
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.text import Text

from registrar.register.types import DatasetOutcome

_PHASE_LABELS = {
    "files": "registering files",
    "share": "creating share",
    "record": "public record",
}


class RichProgressSink:
    """Live progress bar with completed-dataset lines scrolling above."""

    def __init__(self, console: Console, live: Live, progress: Progress):
        self._console = console
        self._live = live
        self._progress = progress
        self._outer_task: TaskID | None = None
        self._inner_task: TaskID | None = None
        self._current_idx = 0
        self._current_name = ""

    def start_dataset(self, idx: int, total: int, name: str, file_count: int) -> None:
        self._current_idx = idx
        self._current_name = name

        if self._outer_task is None:
            self._outer_task = self._progress.add_task("Datasets", total=total)

        self._progress.update(
            self._outer_task,
            description=f"[{idx}/{total}] {name[:40]} — registering files",
        )

        if self._inner_task is not None:
            self._progress.remove_task(self._inner_task)
        self._inner_task = self._progress.add_task("Files", total=file_count)

    def advance_phase(self, phase: Literal["files", "share", "record"]) -> None:
        if self._outer_task is None:
            return

        total_desc = self._progress.tasks[self._outer_task].total or 0
        label = _PHASE_LABELS[phase]
        self._progress.update(
            self._outer_task,
            description=(
                f"[{self._current_idx}/{int(total_desc)}] {self._current_name[:40]} — {label}"
            ),
        )

    def tick_file(self) -> None:
        if self._inner_task is not None:
            self._progress.advance(self._inner_task)

    def finish_dataset(self, outcome: DatasetOutcome) -> None:
        if self._outer_task is not None:
            self._progress.advance(self._outer_task)
        if self._inner_task is not None:
            self._progress.remove_task(self._inner_task)
            self._inner_task = None

        self._console.print(_format_outcome(outcome))


def _format_outcome(outcome: DatasetOutcome) -> Text:
    text = Text()
    text.append(f"  [{outcome.name[:40]}]  ")
    if outcome.success:
        text.append("ok", style="success")
        total_files = outcome.files_registered + outcome.files_skipped
        detail = f"  files {outcome.files_registered}/{total_files}"
        if outcome.share_id:
            detail += f"  share {outcome.share_id}"
        text.append(detail)
    else:
        text.append("FAIL", style="danger")
        text.append(f"  {(outcome.error or '')[:60]}")
    return text


@contextmanager
def progress_for_run(
    console: Console, total: int, space_name: str
) -> Generator[RichProgressSink, None, None]:
    """Context manager that sets up Live + Progress and yields a RichProgressSink.

    Completed datasets are printed to console above the Live area
    (scrolling up like `docker pull`). The progress panel stays pinned.
    """
    console.print(f'\nRegistering {total} datasets into space "{space_name}"\n')

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        expand=False,
    )

    # blank line stays attached to the progress bar (inside Live), so it
    # always separates the bar from the scrolling completed-dataset lines
    # above. printing it before Live would let it scroll up out of place.
    live_content = Padding(Align.center(progress), (1, 0, 0, 0))

    registrar_logger = logging.getLogger("registrar")
    handler_levels: list[tuple[logging.Handler, int]] = []
    for handler in registrar_logger.handlers:
        if hasattr(handler, "console"):
            handler_levels.append((handler, handler.level))
            handler.setLevel(logging.WARNING)

    try:
        with Live(live_content, console=console, refresh_per_second=8) as live:
            yield RichProgressSink(console, live, progress)
    finally:
        for handler, original_level in handler_levels:
            handler.setLevel(original_level)
