"""Plan panels rendered before the y/N confirmation prompt."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from rich.align import Align
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table

from registrar.config import RegisterConfig
from registrar.register.types import TargetPlan


def render_plan_panels(
    plan: TargetPlan, config: RegisterConfig, *, console: Console
) -> RenderableType:
    """Build the two-panel plan display shown before confirmation.

    Both panels are sized to the wider one's natural width and centered
    together, so they share margins on screen.
    """
    panels = [_connection_panel(config), _target_panel(plan, config)]
    width = max(console.measure(p).maximum for p in panels)
    for p in panels:
        p.width = width
    return Align.center(Group(*panels))


# ─────────────────────────────────────────────────────────────────────────────
# Connection panel
# ─────────────────────────────────────────────────────────────────────────────


def _connection_panel(config: RegisterConfig) -> Panel:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold")
    grid.add_column()
    grid.add_column()

    grid.add_row("onezone", config.onedata.onezone_domain, "")
    grid.add_row("oneprovider", config.onedata.oneprovider_domain, "")
    grid.add_row("panel port", str(config.onedata.oneprovider_panel_port), "")

    ssl_annotation = (
        "[danger]! TLS verification disabled[/]" if not config.onedata.verify_ssl else ""
    )
    grid.add_row(
        "verify ssl",
        str(config.onedata.verify_ssl).lower(),
        ssl_annotation,
    )

    return Panel(grid, title="Onedata connection", title_align="left", border_style="info")


# ─────────────────────────────────────────────────────────────────────────────
# Target panel
# ─────────────────────────────────────────────────────────────────────────────


def _target_panel(plan: TargetPlan, config: RegisterConfig) -> Panel:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold")
    grid.add_column(no_wrap=False)
    grid.add_column()

    # space
    space_ann = _created_annotation() if plan.space_id is None else ""
    grid.add_row("space", plan.space_name, space_ann)

    # storage
    storage_ann = _created_annotation() if plan.storage_id is None else ""
    grid.add_row("storage", plan.storage_name, storage_ann)

    # storage endpoint
    endpoint_ann = (
        _inferred_annotation("inferred from first file URL")
        if plan.storage_endpoint_inferred
        else ""
    )
    grid.add_row("storage endpoint", plan.storage_endpoint or "(none)", endpoint_ann)

    # dataset root
    grid.add_row("dataset root", plan.dataset_root or "(top level)", "")

    # sharing
    grid.add_row("sharing", "create shares", "")

    # public data records
    if config.public_data_records.enabled:
        grid.add_row("public records", "enabled", "")
        grid.add_row(
            "handle service",
            config.public_data_records.handle_service_id or "(not set)",
            "",
        )
        grid.add_row("identifier type", config.public_data_records.record_identifier_type, "")
        grid.add_row("identifier policy", config.public_data_records.identifier_policy, "")
    else:
        grid.add_row("public records", "disabled (share only)", "")

    # datasets count
    grid.add_row("datasets", str(plan.datasets_count), "")

    return Panel(grid, title="Registration target", title_align="left", border_style="info")


def _created_annotation() -> str:
    return "[warning]+ will be created[/]"


def _inferred_annotation(detail: str) -> str:
    return f"[dim warning]~ {detail}[/]"
