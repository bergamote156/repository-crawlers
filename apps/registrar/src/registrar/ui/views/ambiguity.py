"""Ambiguity error panel — shown when multiple resources match a name."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from rich.align import Align
from rich.console import RenderableType
from rich.panel import Panel
from rich.text import Text

from registrar.register.planner import AmbiguityError

_MAX_SHOWN_CANDIDATES = 8


def render_ambiguity_panel(exc: AmbiguityError) -> RenderableType:
    """Build the red-bordered panel showing ambiguous candidates and next steps."""
    list_command = "list-spaces" if exc.kind == "space" else "list-storages"
    id_flag = "--space.id" if exc.kind == "space" else "--storage.id"

    lines = Text()
    lines.append(f"{len(exc.candidate_ids)} candidates:\n")
    for cid in exc.candidate_ids[:_MAX_SHOWN_CANDIDATES]:
        lines.append(f"  {cid}\n", style="muted")
    if len(exc.candidate_ids) > _MAX_SHOWN_CANDIDATES:
        extra = len(exc.candidate_ids) - _MAX_SHOWN_CANDIDATES
        lines.append(f"  … ({extra} more)\n", style="muted")

    lines.append("\nregister must be deterministic. Pick one and retry:\n\n")
    lines.append(f"  registrar {list_command}\n", style="code")
    lines.append(f"  registrar register datasets.jsonl {id_flag} <ID>\n", style="code")

    panel = Panel(
        lines,
        title=f'Multiple {exc.kind}s named "{exc.name}" found',
        title_align="left",
        border_style="danger",
        expand=False,
    )
    return Align.center(panel)
