"""
`registrar register` — plan, confirm, apply, run the per-dataset loop.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import sys

import requests

from registrar import output
from registrar.api.onepanel import OnepanelClient
from registrar.api.oneprovider import OneproviderClient
from registrar.api.onezone import OnezoneClient
from registrar.api.utils import MissingTokenError
from registrar.config import RegisterConfig, effective_log_level
from registrar.register.datasets import DatasetsInputError, load_datasets
from registrar.register.planner import (
    AmbiguityError,
    TargetResolutionError,
    build_target_plan,
)
from registrar.register.registration import run_registration
from registrar.register.render import (
    confirm,
    render_ambiguity,
    render_plan,
    render_summary,
)
from registrar.register.types import OnedataClients, ResolvedTarget, TargetPlan


def run(config: RegisterConfig) -> int:
    """Plan, confirm, apply, and run registration of datasets into Onedata."""
    output.set_level(effective_log_level(config.logging))

    try:
        clients = OnedataClients(
            onepanel=OnepanelClient.from_config(config),
            onezone=OnezoneClient.from_config(config),
            oneprovider=OneproviderClient.from_config(config),
        )
        datasets = load_datasets(config.datasets_file)
        plan = build_target_plan(config, clients.onepanel, datasets)
    except AmbiguityError as exc:
        return _fail(render_ambiguity(exc))
    except (MissingTokenError, DatasetsInputError, TargetResolutionError) as exc:
        return _fail(str(exc))
    except requests.RequestException as exc:
        return _fail(f"failed to query Onepanel: {exc}")

    sys.stdout.write(render_plan(plan, config))
    sys.stdout.write("\n\n")
    sys.stdout.flush()

    if not confirm(assume_yes=config.yes):
        sys.stdout.write("Registration cancelled.\n")
        return 0

    try:
        target = _apply_target_plan(
            plan, clients=clients, storage_default_size=config.storage_default_size
        )
    except requests.RequestException as exc:
        return _fail(f"failed to apply target plan: {exc}")

    sys.stdout.write("\n")
    summary = run_registration(
        target,
        datasets,
        config,
        oneprovider=clients.oneprovider,
        onezone=clients.onezone,
    )
    sys.stdout.write(render_summary(summary))
    sys.stdout.flush()

    return 0 if summary.failed == 0 else 1


def _fail(message: str) -> int:
    sys.stderr.write(f"error: {message}\n")
    return 1


def _apply_target_plan(
    plan: TargetPlan,
    *,
    clients: OnedataClients,
    storage_default_size: int,
) -> ResolvedTarget:
    """Materialize the plan: storage first, then space, then support.

    Order matters — a freshly-minted storage ID must be available before
    `support_space` runs.
    """
    storage_id = plan.storage_id
    if storage_id is None:
        storage_id = clients.onepanel.add_storage(
            name=plan.storage_name, endpoint=plan.storage_endpoint
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
