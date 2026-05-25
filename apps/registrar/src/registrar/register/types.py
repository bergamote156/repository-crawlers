"""Cross-module data contracts for the `register` command."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass

from registrar.api.onepanel import OnepanelClient
from registrar.api.oneprovider import OneproviderClient
from registrar.api.onezone import OnezoneClient

# ─────────────────────────────────────────────────────────────────────────────
# API clients
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OnedataClients:
    """API client bundle for a single registrar run."""

    onepanel: OnepanelClient
    onezone: OnezoneClient
    oneprovider: OneproviderClient


# ─────────────────────────────────────────────────────────────────────────────
# Target — planner output, applier output
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TargetPlan:
    """Resolved registration target plus the work needed to bring it about.

    `space_id` / `storage_id` are `None` when the resource will be
    created in this run; `needs_support` is `True` when the resolved
    storage does not yet support the resolved space.

    The HTTP storage option fields reflect the values that will be in
    effect after the run: for an existing storage the values read from
    Onepanel, for a freshly-planned one the values from the config.
    `storage_max_emulated_range_read_file_size` is `None` when no limit
    is being requested — at create time the key is omitted so Onepanel
    applies its own default.
    """

    space_name: str
    space_id: str | None
    space_inferred: bool
    """`True` when `space_name` was inferred from the first file URL."""

    storage_name: str
    storage_id: str | None
    storage_endpoint: str
    storage_endpoint_inferred: bool
    storage_emulate_range_read: bool
    storage_max_emulated_range_read_file_size: int | None

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
class FailedDataset:
    """Name and error message for a dataset that failed registration."""

    name: str
    error: str


@dataclass(frozen=True)
class Summary:
    """Aggregate of a complete `run_registration` invocation."""

    total: int
    successful: int
    files_registered: int
    files_skipped: int
    shares_count: int
    records_count: int
    failures: tuple[FailedDataset, ...]

    @property
    def failed(self) -> int:
        return len(self.failures)
