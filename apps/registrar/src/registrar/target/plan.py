"""Plan dataclasses."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass


@dataclass(frozen=True)
class TargetPlan:
    """Resolved registration target plus the work needed to bring it about.

    `space_id` / `storage_id` are `None` when the resource will be
    created in this run; `needs_support` is `True` when the resolved
    storage does not yet support the resolved space.
    """

    space_name: str
    space_id: str | None
    space_inferred: bool
    """`True` when `space_name` was inferred from the first file URL."""

    storage_name: str
    storage_id: str | None
    storage_endpoint: str
    storage_endpoint_inferred: bool

    dataset_root: str
    datasets_count: int

    needs_support: bool


@dataclass(frozen=True)
class ResolvedTarget:
    """The single registration target every dataset in the run uses.

    Output of `apply_target_plan` — every action implied by the plan
    has run, so all IDs are concrete.
    """

    space_id: str
    space_name: str
    storage_id: str
    dataset_root: str
