"""Plan rendering and the interactive confirmation prompt."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import sys

from registrar.config import RegisterConfig
from registrar.target.plan import TargetPlan


def render_plan(plan: TargetPlan, config: RegisterConfig) -> str:
    """Format the plan as the multi-line block shown in registrar_ui.md."""
    lines: list[str] = []

    lines.append("Onedata connection:")
    lines.append(f"  onezone: {config.onedata.oz_domain}")
    lines.append(f"  oneprovider: {config.onedata.op_domain}")
    lines.append(f"  panel port: {config.onedata.op_panel_port}")
    lines.append(f"  verify ssl: {_yesno(config.onedata.verify_ssl)}")
    lines.append("")

    lines.append("Registration target:")
    lines.append(f"  space: {_format_space(plan)}")
    lines.append(f"  storage: {_format_storage(plan)}")
    lines.append(f"  storage endpoint: {_format_endpoint(plan)}")
    lines.append(f"  dataset root: {plan.dataset_root or '(top level)'}")
    lines.append("  sharing: create shares")
    lines.append(f"  public data records: {_format_records_enabled(config)}")
    lines.append(f"  handle service: {_format_handle_service(config)}")
    lines.append(f"  public identifier type: {config.public_data_records.public_identifier_type}")
    lines.append(f"  identifier policy: {config.public_data_records.identifier_policy}")
    lines.append(f"  datasets: {plan.datasets_count}")
    lines.append("")
    lines.append("All datasets from this run will be registered into one space.")

    return "\n".join(lines)


def confirm(*, assume_yes: bool) -> bool:
    """Prompt for `y/N`. Returns True on confirmation.

    Returns True immediately when `assume_yes` is set. Anything other
    than `y` / `Y` (or `yes` / `YES`) returns False, including EOF —
    matching the `[y/N]` default-no convention shown in the prompt.
    """
    if assume_yes:
        return True

    try:
        answer = input("Continue? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        sys.stdout.write("\n")
        return False
    return answer.strip().lower() in ("y", "yes")


# ─────────────────────────────────────────────────────────────────────────────
# Per-line formatters
# ─────────────────────────────────────────────────────────────────────────────


def _format_space(plan: TargetPlan) -> str:
    annotations: list[str] = []
    if plan.space_id is None:
        annotations.append("will be created")
    if plan.space_inferred:
        annotations.append("inferred from first file")
    if plan.space_id is not None:
        annotations.append(f"id {plan.space_id}")
    return _with_annotations(plan.space_name, annotations)


def _format_storage(plan: TargetPlan) -> str:
    annotations: list[str] = []
    if plan.storage_id is None:
        annotations.append("will be created")
    if plan.storage_id is not None:
        annotations.append(f"id {plan.storage_id}")
    return _with_annotations(plan.storage_name, annotations)


def _format_endpoint(plan: TargetPlan) -> str:
    if plan.storage_endpoint_inferred:
        return f"{plan.storage_endpoint} (inferred from first file)"
    return plan.storage_endpoint or "(none)"


def _format_records_enabled(config: RegisterConfig) -> str:
    return "enabled" if config.public_data_records.register else "disabled (share only)"


def _format_handle_service(config: RegisterConfig) -> str:
    handle_service_id = config.public_data_records.handle_service_id
    if not handle_service_id:
        return "(not set)"
    return handle_service_id


def _with_annotations(value: str, annotations: list[str]) -> str:
    if not annotations:
        return value
    return f"{value} ({', '.join(annotations)})"


def _yesno(flag: bool) -> str:
    return "true" if flag else "false"
