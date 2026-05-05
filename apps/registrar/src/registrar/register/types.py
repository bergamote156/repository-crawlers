"""
Cross-module data contracts for the `register` command.

`TargetPlan` and `ResolvedTarget` describe the registration target before
and after the planner+applier round-trip. `DatasetOutcome` and `Summary`
describe per-dataset and aggregate results of the registration loop.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass

# ─────────────────────────────────────────────────────────────────────────────
# Target — planner output, applier output
# ─────────────────────────────────────────────────────────────────────────────


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

    Output of the applier — every action implied by the plan has run,
    so all IDs are concrete.
    """

    space_id: str
    space_name: str
    storage_id: str
    dataset_root: str


# ─────────────────────────────────────────────────────────────────────────────
# Registration loop — per-dataset and aggregate results
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DatasetOutcome:
    """Result of registering a single dataset.

    `record_identifier` is `None` when public-data records are disabled
    (`--share-only`) or the dataset failed before reaching that step.
    """

    name: str
    success: bool
    files_registered: int = 0
    files_skipped: int = 0
    share_id: str | None = None
    record_identifier: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class Summary:
    """Aggregate of a complete `run_registration` invocation."""

    outcomes: tuple[DatasetOutcome, ...]

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def successful(self) -> int:
        return sum(1 for o in self.outcomes if o.success)

    @property
    def failed(self) -> int:
        return sum(1 for o in self.outcomes if not o.success)

    @property
    def files_registered(self) -> int:
        return sum(o.files_registered for o in self.outcomes)

    @property
    def files_skipped(self) -> int:
        return sum(o.files_skipped for o in self.outcomes)

    @property
    def shares_count(self) -> int:
        return sum(1 for o in self.outcomes if o.share_id)

    @property
    def records_count(self) -> int:
        return sum(1 for o in self.outcomes if o.record_identifier)
