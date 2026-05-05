"""
Operator-visible output for `registrar register`.

Covers everything the operator sees during a register run: the pre-confirm
plan block, the y/N prompt, the per-dataset progress tail, the closing
summary, and the ambiguity-error message the orchestrator prints to stderr.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import sys

from registrar.config import RegisterConfig
from registrar.register.planner import AmbiguityError
from registrar.register.types import DatasetOutcome, Summary, TargetPlan


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


def render_outcome_tail(outcome: DatasetOutcome) -> str:
    """Per-dataset progress tail printed after `[i/N] name ...` during the loop."""
    if not outcome.success:
        return f"FAIL: {outcome.error}"

    parts = [
        f"OK ({outcome.files_registered} registered, {outcome.files_skipped} skipped)",
    ]
    if outcome.share_id:
        parts.append(f"share {outcome.share_id}")
    if outcome.record_identifier:
        parts.append(f"record {outcome.record_identifier}")

    return "; ".join(parts)


def render_summary(summary: Summary) -> str:
    """Closing report printed once `run_registration` returns."""
    bar = "═" * 70
    lines: list[str] = ["", bar, "Registration complete", bar]
    lines.append(
        f"Datasets: {summary.total} total, "
        f"{summary.successful} successful, {summary.failed} failed",
    )
    lines.append(
        f"Files:    {summary.files_registered} registered, {summary.files_skipped} skipped",
    )
    lines.append(f"Shares:   {summary.shares_count} created or reused")
    lines.append(f"Records:  {summary.records_count} public-data-record identifiers")
    lines.append(bar)
    if summary.failed:
        lines.append("")
        lines.append("Failed datasets:")
        for outcome in summary.outcomes:
            if not outcome.success:
                lines.append(f"  - {outcome.name}: {outcome.error}")

    return "\n".join(lines) + "\n"


def render_ambiguity(exc: AmbiguityError) -> str:
    """Operator-facing message for `AmbiguityError` — pointer to `list-*` and `--*.id`."""
    list_command = "list-spaces" if exc.kind == "space" else "list-storages"
    id_flag = "--space.id" if exc.kind == "space" else "--storage.id"
    candidates = ", ".join(exc.candidate_ids)
    return (
        f"multiple {exc.kind} resources named {exc.name!r} found "
        f"(IDs: {candidates}).\n"
        f"Run `registrar {list_command}` and retry with {id_flag}."
    )


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
