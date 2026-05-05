"""
Plan applier — creates the missing space/storage and adds support
implied by `TargetPlan`, returning the resolved registration target.

The side-effecting counterpart of `build_target_plan`. Always runs
in the same order: create the storage, then the space, then add
support — so a freshly-minted ID is available for the support call.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from registrar.api.onepanel import OnepanelClient
from registrar.api.onezone import OnezoneClient
from registrar.target.plan import ResolvedTarget, TargetPlan


def apply_target_plan(
    plan: TargetPlan,
    *,
    onepanel: OnepanelClient,
    onezone: OnezoneClient,
    storage_default_size: int,
) -> ResolvedTarget:
    """Execute the work implied by `plan` and return the resolved target."""
    storage_id = plan.storage_id
    if storage_id is None:
        storage_id = onepanel.add_storage(name=plan.storage_name, endpoint=plan.storage_endpoint)

    space_id = plan.space_id
    if space_id is None:
        space_id = onezone.create_space(name=plan.space_name)

    if plan.needs_support:
        support_token = onezone.create_support_token(space_id)
        onepanel.support_space(
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
