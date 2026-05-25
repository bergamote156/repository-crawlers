"""
`registrar register` — plan, confirm, apply, run the per-dataset loop.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import requests
from rich.prompt import Confirm

from registrar.api.onepanel import OnepanelClient
from registrar.api.oneprovider import OneproviderClient
from registrar.api.onezone import OnezoneClient
from registrar.api.utils import MissingTokenError
from registrar.config import RegisterConfig, effective_log_level
from registrar.logging_config import setup_logging
from registrar.register.datasets import DatasetsInputError, load_datasets
from registrar.register.planner import (
    AmbiguityError,
    TargetResolutionError,
    build_target_plan,
)
from registrar.register.registration import run_registration
from registrar.register.types import OnedataClients, ResolvedTarget, TargetPlan
from registrar.run_artifacts import create_run_dir, dump_config, dump_summary
from registrar.ui.console import get_console
from registrar.ui.views.ambiguity import render_ambiguity_panel
from registrar.ui.views.plan import render_plan_panels
from registrar.ui.views.progress import progress_for_run
from registrar.ui.views.summary import render_summary


def run(config: RegisterConfig) -> int:
    """Plan, confirm, apply, and run registration of datasets into Onedata."""
    console = get_console()
    run_dir = create_run_dir(config.output.dir)
    setup_logging(
        console=console,
        level=effective_log_level(config.logging),
        run_dir=run_dir,
    )
    dump_config(run_dir, config)

    try:
        clients = OnedataClients(
            onepanel=OnepanelClient.from_config(config),
            onezone=OnezoneClient.from_config(config),
            oneprovider=OneproviderClient.from_config(config),
        )
        datasets = load_datasets(config.datasets_file)
        plan = build_target_plan(config, clients.onepanel, datasets)
    except AmbiguityError as exc:
        console.print(render_ambiguity_panel(exc))
        return 1
    except (MissingTokenError, DatasetsInputError, TargetResolutionError) as exc:
        console.print(f"[danger]error:[/] {exc}")
        return 1
    except requests.RequestException as exc:
        console.print(f"[danger]error:[/] failed to query Onepanel: {exc}")
        return 1

    console.print()
    console.print(render_plan_panels(plan, config, console=console))
    console.print("\nAll datasets from this run will be registered into one space.")

    if not Confirm.ask("Continue?", default=False):
        console.print("[muted]Registration cancelled.[/]")
        return 0

    try:
        target = _apply_target_plan(
            plan, clients=clients, storage_default_size=config.storage_options.default_size
        )
    except requests.RequestException as exc:
        console.print(f"[danger]error:[/] failed to apply target plan: {exc}")
        return 1

    with progress_for_run(console, len(datasets), plan.space_name) as sink:
        summary = run_registration(
            target,
            datasets,
            config,
            oneprovider=clients.oneprovider,
            onezone=clients.onezone,
            progress_sink=sink,
        )

    dump_summary(run_dir, summary)
    console.print()
    console.print(render_summary(summary, run_dir=run_dir))
    return 0 if summary.failed == 0 else 1


def _apply_target_plan(
    plan: TargetPlan,
    *,
    clients: OnedataClients,
    storage_default_size: int,
) -> ResolvedTarget:
    """Materialize the plan: storage first, then space, then support."""
    storage_id = plan.storage_id
    if storage_id is None:
        storage_id = clients.onepanel.add_storage(
            name=plan.storage_name,
            endpoint=plan.storage_endpoint,
            emulate_range_read=plan.storage_emulate_range_read,
            max_emulated_range_read_file_size=plan.storage_max_emulated_range_read_file_size,
        )

    space_id = plan.space_id
    if space_id is None:
        space_id = clients.onezone.create_space(name=plan.space_name)

    if plan.needs_support:
        support_token = clients.onezone.create_support_token(space_id)
        clients.onepanel.support_space(
            storage_id=storage_id,
            support_token=support_token,
            size=storage_default_size,
        )

    return ResolvedTarget(
        space_id=space_id,
        space_name=plan.space_name,
        storage_id=storage_id,
        dataset_root=plan.dataset_root,
    )
