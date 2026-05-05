"""
Target plan orchestrator — cascades through space/storage selection and
calls the lookup layer only when needed.

Conventions:

- An explicit `space.id` always wins over `space.name`; the mutex
  group at the config layer prevents the user from supplying both.
- Storage compatibility means HTTP readonly imported, matching the
  payload that `OnepanelClient.add_storage` writes.
- The planner refuses to choose between candidates with the same name.
  Ambiguity surfaces as `AmbiguityError`, which the CLI handler turns
  into the operator-facing message described in the spec.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from collections.abc import Sequence
from dataclasses import dataclass

from onedata_dataset import OnedataDataset
from registrar.api.onepanel import OnepanelClient
from registrar.config import RegisterConfig, SpaceSelection, StorageSelection
from registrar.target.lookups import (
    choose_endpoint,
    find_spaces_by_name,
    find_storages_by_name,
    infer_domain,
    is_storage_compatible,
    lookup_space_by_id,
    lookup_storage_by_id,
)
from registrar.target.plan import TargetPlan

# ─────────────────────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────────────────────


class TargetResolutionError(RuntimeError):
    """A precondition for building a plan is unmet (bad ID, missing token, …)."""


class AmbiguityError(TargetResolutionError):
    """Multiple resources match the given name; `register` refuses to choose."""

    def __init__(self, *, kind: str, name: str, candidate_ids: tuple[str, ...]) -> None:
        super().__init__(f"multiple {kind} resources named {name!r}: {len(candidate_ids)} matches")
        self.kind = kind
        self.name = name
        self.candidate_ids = candidate_ids


# ─────────────────────────────────────────────────────────────────────────────
# Internal records (planner-side, decorated with policy bits)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _PlannedSpace:
    name: str
    id: str | None
    """`None` when the space will be created in this run."""
    inferred: bool
    current_storage_id: str | None
    """Storage currently supporting the space on this provider, if any."""


@dataclass(frozen=True)
class _PlannedStorage:
    name: str
    id: str | None
    """`None` when the storage will be created in this run."""
    endpoint: str
    endpoint_inferred: bool


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────


def build_target_plan(
    config: RegisterConfig,
    onepanel: OnepanelClient,
    datasets: Sequence[OnedataDataset],
) -> TargetPlan:
    """Plan the registration target from `config` against current provider state.

    Returns a frozen `TargetPlan`; raises `TargetResolutionError` (or
    one of its subclasses) when the plan cannot be built deterministically.
    """
    if not datasets:
        raise TargetResolutionError("datasets list is empty — nothing to plan against.")

    first_file_url = _first_file_url(datasets)
    space = _resolve_space(onepanel, config.space, first_file_url)
    storage = _resolve_storage(
        onepanel,
        config.storage,
        space,
        explicit_endpoint=config.storage_endpoint,
        first_file_url=first_file_url,
    )

    return TargetPlan(
        space_name=space.name,
        space_id=space.id,
        space_inferred=space.inferred,
        storage_name=storage.name,
        storage_id=storage.id,
        storage_endpoint=storage.endpoint,
        storage_endpoint_inferred=storage.endpoint_inferred,
        dataset_root=config.dataset_root,
        datasets_count=len(datasets),
        # Single-support invariant (a space can be supported by only one
        # storage on a provider) is enforced inside _resolve_storage. So when
        # both IDs land non-None the resolved storage already supports the
        # resolved space, and `support_space` only runs for fresh creations.
        needs_support=(space.id is None or storage.id is None),
    )


def _first_file_url(datasets: Sequence[OnedataDataset]) -> str:
    """First file URL across the datasets, or '' when none have files."""
    for dataset in datasets:
        if dataset.files and dataset.files[0].url:
            return dataset.files[0].url

    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Space resolution
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_space(
    onepanel: OnepanelClient,
    selection: SpaceSelection,
    first_file_url: str,
) -> _PlannedSpace:
    if selection.id:
        details = lookup_space_by_id(onepanel, selection.id)
        if details is None:
            raise TargetResolutionError(
                f"space ID {selection.id!r} not found on this provider — "
                "verify the ID via `registrar list-spaces`.",
            )

        return _PlannedSpace(
            name=details["name"],
            id=selection.id,
            inferred=False,
            current_storage_id=details["storageId"],
        )

    if selection.name:
        return _resolve_space_by_name(onepanel, selection.name, inferred=False)

    inferred_name = infer_domain(first_file_url)
    if inferred_name:
        return _resolve_space_by_name(onepanel, inferred_name, inferred=True)

    raise TargetResolutionError(
        "no space name/id was given and the first dataset has no usable "
        "file URL — cannot infer a target.",
    )


def _resolve_space_by_name(
    onepanel: OnepanelClient,
    name: str,
    *,
    inferred: bool,
) -> _PlannedSpace:
    matches = find_spaces_by_name(onepanel, name)
    if not matches:
        return _PlannedSpace(name=name, id=None, inferred=inferred, current_storage_id=None)

    if len(matches) == 1:
        space_id, details = matches[0]
        return _PlannedSpace(
            name=name,
            id=space_id,
            inferred=inferred,
            current_storage_id=details["storageId"],
        )

    raise AmbiguityError(
        kind="space",
        name=name,
        candidate_ids=tuple(m[0] for m in matches),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Storage resolution
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_storage(
    onepanel: OnepanelClient,
    selection: StorageSelection,
    space: _PlannedSpace,
    *,
    explicit_endpoint: str,
    first_file_url: str,
) -> _PlannedStorage:
    if selection.id:
        return _resolve_storage_by_id(onepanel, selection.id, space)

    if selection.name:
        return _resolve_storage_by_name(
            onepanel,
            selection.name,
            space,
            explicit_endpoint=explicit_endpoint,
            first_file_url=first_file_url,
        )

    # Auto path. The space already has a current support if `space.id` was
    # resolved (Onepanel only lists spaces it supports), so we either reuse
    # that support or fall through to use-or-create with the space name.
    if space.current_storage_id is not None:
        current = lookup_storage_by_id(onepanel, space.current_storage_id)
        if current is None:
            raise TargetResolutionError(
                f"space {space.id!r} reports current support {space.current_storage_id!r} "
                "but the storage was not found on this provider.",
            )

        if not is_storage_compatible(current):
            raise TargetResolutionError(
                f"space {space.id!r} is supported by storage {space.current_storage_id!r} "
                "which is not HTTP readonly imported; a space can be supported by only "
                "one storage on a provider, so the planner cannot add a compatible one.",
            )

        return _PlannedStorage(
            name=current["name"],
            id=space.current_storage_id,
            endpoint=current.get("endpoint", ""),
            endpoint_inferred=False,
        )

    return _resolve_storage_by_name(
        onepanel,
        space.name,
        space,
        explicit_endpoint=explicit_endpoint,
        first_file_url=first_file_url,
    )


def _resolve_storage_by_id(
    onepanel: OnepanelClient,
    storage_id: str,
    space: _PlannedSpace,
) -> _PlannedStorage:
    details = lookup_storage_by_id(onepanel, storage_id)
    if details is None:
        raise TargetResolutionError(
            f"storage ID {storage_id!r} not found on this provider — "
            "verify the ID via `registrar list-storages`.",
        )

    if not is_storage_compatible(details):
        raise TargetResolutionError(
            f"storage {storage_id!r} is not an HTTP readonly imported storage "
            "and cannot be used for file registration.",
        )

    _enforce_single_support(space, storage_id)

    return _PlannedStorage(
        name=details["name"],
        id=storage_id,
        endpoint=details.get("endpoint", ""),
        endpoint_inferred=False,
    )


def _resolve_storage_by_name(
    onepanel: OnepanelClient,
    name: str,
    space: _PlannedSpace,
    *,
    explicit_endpoint: str,
    first_file_url: str,
) -> _PlannedStorage:
    matches = find_storages_by_name(onepanel, name)
    if len(matches) > 1:
        raise AmbiguityError(
            kind="storage",
            name=name,
            candidate_ids=tuple(m[0] for m in matches),
        )

    if len(matches) == 1:
        storage_id, details = matches[0]
        if not is_storage_compatible(details):
            raise TargetResolutionError(
                f"storage named {name!r} (ID {storage_id!r}) is not an HTTP readonly "
                "imported storage and cannot be used for file registration.",
            )

        _enforce_single_support(space, storage_id)

        return _PlannedStorage(
            name=name,
            id=storage_id,
            endpoint=details.get("endpoint", ""),
            endpoint_inferred=False,
        )

    # Plan to create a new storage with this name. A space that's already
    # supported can't switch to a freshly-created one — the single-support
    # invariant blocks that.
    if space.current_storage_id is not None:
        raise TargetResolutionError(
            f"no storage named {name!r} on this provider, and space {space.id!r} "
            f"is already supported by {space.current_storage_id!r}; cannot create "
            "and attach a second support.",
        )

    chosen = choose_endpoint(explicit_endpoint, first_file_url)
    if chosen is None:
        raise TargetResolutionError(
            f"cannot infer storage endpoint from {first_file_url!r} — "
            "pass storage endpoint explicitly.",
        )

    endpoint, endpoint_inferred = chosen
    return _PlannedStorage(
        name=name,
        id=None,
        endpoint=endpoint,
        endpoint_inferred=endpoint_inferred,
    )


def _enforce_single_support(space: _PlannedSpace, resolved_storage_id: str) -> None:
    """Refuse to plan a switch of a space's existing support."""
    if space.current_storage_id is None or space.current_storage_id == resolved_storage_id:
        return

    raise TargetResolutionError(
        f"space {space.id!r} is already supported by storage "
        f"{space.current_storage_id!r}; a space can be supported by only one storage "
        f"on a provider, so the planner cannot switch to {resolved_storage_id!r}.",
    )
