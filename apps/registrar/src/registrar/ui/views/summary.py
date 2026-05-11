"""Registration summary view — closing report after the loop completes."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from pathlib import Path

from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text, TextType

from registrar.register.types import Summary


def render_summary(summary: Summary, *, run_dir: Path | None = None) -> RenderableType:
    """Build the full closing summary renderable."""
    parts: list[RenderableType] = []

    # rule
    rule_style, title = _rule_style_and_title(summary)
    parts.append(Rule(title=title, style=rule_style))

    # stats table
    if summary.total > 0:
        parts.append(_stats_table(summary))

    # failures panel
    if summary.failed > 0:
        parts.append(Align.center(_failures_panel(summary)))

    # artifacts footer
    if run_dir is not None:
        parts.append(_artifacts_footer(run_dir))

    return Group(*parts)


# ─────────────────────────────────────────────────────────────────────────────
# Components
# ─────────────────────────────────────────────────────────────────────────────


def _rule_style_and_title(summary: Summary) -> tuple[str, str]:
    if summary.successful == 0 and summary.total > 0:
        return "danger", "Registration failed"

    if summary.failed > 0:
        return "warning", "Registration complete with failures"

    return "success", "Registration complete"


def _stats_table(summary: Summary) -> Table:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold", justify="right")
    grid.add_column(justify="right")
    grid.add_column()

    grid.add_row(
        "Datasets",
        str(summary.total) + " total",
        _styled_counts(summary),
    )
    grid.add_row(
        "Files",
        f"{summary.files_registered:,} registered",
        f"{summary.files_skipped:,} skipped",
    )
    grid.add_row("Shares", f"{summary.shares_count:,} created or reused", "")
    grid.add_row("Records", f"{summary.records_count:,} public-data-record identifiers", "")
    return grid


def _failures_panel(summary: Summary) -> Panel:
    max_inline = 8
    lines = Text()
    for failure in summary.failures[:max_inline]:
        error = failure.error.replace("\n", " ")[:80]
        lines.append(f"  {failure.name:<30}  {error}\n")

    if len(summary.failures) > max_inline:
        remaining = len(summary.failures) - max_inline
        lines.append(f"  … ({remaining} more — see registration.log)\n", style="muted")

    style = "warning" if summary.successful > 0 else "danger"
    return Panel(
        lines,
        title=f"Failed datasets ({summary.failed})",
        title_align="left",
        border_style=style,
        expand=False,
    )


def _artifacts_footer(run_dir: Path) -> Text:
    text = Text()
    text.append("\nRun artifacts:  ", style="bold")
    text.append(str(run_dir) + "/", style="info")
    text.append("\n  registration.log    config.yaml    summary.json", style="muted")
    text.append("\n")
    return text


def _styled_counts(summary: Summary) -> TextType:
    text = Text()
    if summary.failed == 0:
        text.append(f"{summary.successful} successful", style="success")
    else:
        text.append(f"{summary.successful} successful")

    text.append("     ")
    if summary.failed > 0:
        text.append(f"{summary.failed} failed", style="danger")
    else:
        text.append(f"{summary.failed} failed")

    return text
