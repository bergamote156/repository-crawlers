"""
Registration loop — run the resolved target against a list of datasets.

Public surface:

- `run_registration` — orchestrator called by `RegistrarApp.register` after
  the plan has been confirmed and applied.
- `RecordRequirementError` — typed per-dataset failure for the
  identifier-policy / public-identifier-type combinations a dataset cannot
  satisfy. The runner converts it into a failed outcome and continues.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import sys
from collections.abc import Sequence

import requests

from onedata_dataset import OnedataDataset
from registrar.api.oneprovider import OneproviderClient
from registrar.api.onezone import OnezoneClient
from registrar.config import PublicDataRecords, RegisterConfig
from registrar.register.render import render_outcome_tail
from registrar.register.types import DatasetOutcome, FailedDataset, ResolvedTarget, Summary

# ─────────────────────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────────────────────


class RecordRequirementError(RuntimeError):
    """A dataset cannot satisfy the configured identifier policy.

    Raised per-dataset; the runner converts it into a failed
    `DatasetOutcome` and continues with the next dataset.
    """


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────


def run_registration(
    target: ResolvedTarget,
    datasets: Sequence[OnedataDataset],
    config: RegisterConfig,
    *,
    oneprovider: OneproviderClient,
    onezone: OnezoneClient,
) -> Summary:
    """Walk `datasets`, register each, and return the aggregated `Summary`."""
    total = len(datasets)
    successful = 0
    files_registered = 0
    files_skipped = 0
    shares_count = 0
    records_count = 0
    failures: list[FailedDataset] = []

    for idx, dataset in enumerate(datasets, 1):
        prefix = f"[{idx}/{total}] {dataset.name or '(unnamed)'}"
        sys.stdout.write(f"{prefix} ... ")
        sys.stdout.flush()
        outcome = _process_one(target, dataset, config, oneprovider, onezone)
        sys.stdout.write(render_outcome_tail(outcome) + "\n")
        sys.stdout.flush()

        if outcome.success:
            successful += 1
            files_registered += outcome.files_registered
            files_skipped += outcome.files_skipped
            if outcome.share_id:
                shares_count += 1
            if outcome.record_identifier:
                records_count += 1
        else:
            failures.append(FailedDataset(name=outcome.name, error=outcome.error or ""))

    return Summary(
        total=total,
        successful=successful,
        files_registered=files_registered,
        files_skipped=files_skipped,
        shares_count=shares_count,
        records_count=records_count,
        failures=tuple(failures),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Per-dataset orchestration
# ─────────────────────────────────────────────────────────────────────────────


def _process_one(
    target: ResolvedTarget,
    dataset: OnedataDataset,
    config: RegisterConfig,
    oneprovider: OneproviderClient,
    onezone: OnezoneClient,
) -> DatasetOutcome:
    dataset_dir = _join_paths(target.dataset_root, dataset.target_dir)

    try:
        registered, skipped = _register_files(target, dataset, dataset_dir, oneprovider)
        share_id = _ensure_share(target, dataset, dataset_dir, oneprovider)
        record_identifier: str | None = None
        if config.public_data_records.register:
            record_identifier = _ensure_public_record(
                config=config.public_data_records,
                dataset=dataset,
                share_id=share_id,
                onezone=onezone,
                oneprovider=oneprovider,
            )
    except RecordRequirementError as exc:
        return DatasetOutcome(name=dataset.name, success=False, error=str(exc))
    except requests.RequestException as exc:
        return DatasetOutcome(name=dataset.name, success=False, error=str(exc))
    except RuntimeError as exc:
        # catches our own internal raises (e.g. dataset_dir lookup miss)
        return DatasetOutcome(name=dataset.name, success=False, error=str(exc))

    return DatasetOutcome(
        name=dataset.name,
        success=True,
        files_registered=registered,
        files_skipped=skipped,
        share_id=share_id,
        record_identifier=record_identifier,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Per-step helpers — files, share, public-data record
# ─────────────────────────────────────────────────────────────────────────────


def _register_files(
    target: ResolvedTarget,
    dataset: OnedataDataset,
    dataset_dir: str,
    oneprovider: OneproviderClient,
) -> tuple[int, int]:
    registered = 0
    skipped = 0
    for file_info in dataset.files:
        file_path = file_info.path.strip("/")
        dest_path = f"{dataset_dir}/{file_path}" if dataset_dir else file_path

        existing = oneprovider.lookup_file_id(space_name=target.space_name, path=dest_path)
        if existing:
            skipped += 1
            continue

        oneprovider.register_file(
            storage_id=target.storage_id,
            space_id=target.space_id,
            file_url=file_info.url,
            dest_path=dest_path,
        )
        registered += 1
    return registered, skipped


def _ensure_share(
    target: ResolvedTarget,
    dataset: OnedataDataset,
    dataset_dir: str,
    oneprovider: OneproviderClient,
) -> str:
    file_id = oneprovider.lookup_file_id(space_name=target.space_name, path=dataset_dir)
    if not file_id:
        raise RuntimeError(
            f"could not look up dataset directory {dataset_dir!r} after file registration",
        )

    return _find_or_create_share(
        oneprovider,
        file_id=file_id,
        name=dataset.name,
        description=dataset.name,
    )


def _find_or_create_share(
    oneprovider: OneproviderClient,
    *,
    file_id: str,
    name: str,
    description: str,
) -> str:
    file_attrs = oneprovider.get_file_attrs(file_id) or {}
    for share_id in file_attrs.get("shares") or ():
        details = oneprovider.get_share_details(share_id) or {}
        if details.get("name") == name and details.get("description") == description:
            return share_id

    return oneprovider.create_share(file_id=file_id, name=name, description=description)


def _ensure_public_record(
    *,
    config: PublicDataRecords,
    dataset: OnedataDataset,
    share_id: str,
    onezone: OnezoneClient,
    oneprovider: OneproviderClient,
) -> str:
    """Return the public-data-record identifier for `dataset`.

    Dispatches on `public_identifier_type`: share URLs are derived from the
    share itself, handles always go through the Onezone handle-registration
    endpoint (which both mints new handles and attaches existing PIDs).
    """
    if config.public_identifier_type == "onedata-url":
        return _resolve_share_url(config, dataset, share_id, onezone, oneprovider)
    return _resolve_handle(config, dataset, share_id, onezone, oneprovider)


def _resolve_share_url(
    config: PublicDataRecords,
    dataset: OnedataDataset,
    share_id: str,
    onezone: OnezoneClient,
    oneprovider: OneproviderClient,
) -> str:
    """Pick the share-URL identifier per `identifier_policy`.

    No handle service is involved — `dataset.pid` here is treated as an
    upstream-published share URL the registrar should record as-is.
    """
    pid = dataset.pid
    if config.identifier_policy == "always-reuse-existing":
        if not pid:
            raise RecordRequirementError(
                "identifier_policy=always-reuse-existing requires dataset.pid; got none.",
            )
        return pid
    if config.identifier_policy == "generate-new-if-missing" and pid:
        return pid
    return _share_public_url(share_id, onezone.domain, oneprovider)


def _resolve_handle(
    config: PublicDataRecords,
    dataset: OnedataDataset,
    share_id: str,
    onezone: OnezoneClient,
    oneprovider: OneproviderClient,
) -> str:
    """Ensure a public handle for the share and return its ID.

    If the share already carries a handle, reuse it. Otherwise call
    `register_handle` once — passing `pid_to_reuse` for reuse policies and
    `None` when the policy demands a freshly minted handle.
    """
    if not dataset.metadata_xml:
        raise RecordRequirementError(
            "public_identifier_type=handle-service requires the dataset to provide metadata_xml.",
        )

    details = oneprovider.get_share_details(share_id) or {}
    existing = details.get("handleId")
    if existing:
        return existing

    pid = dataset.pid
    if config.identifier_policy == "always-reuse-existing":
        if not pid:
            raise RecordRequirementError(
                "identifier_policy=always-reuse-existing requires dataset.pid; got none.",
            )
        pid_to_reuse: str | None = pid
    elif config.identifier_policy == "generate-new-if-missing" and pid:
        pid_to_reuse = pid
    else:
        pid_to_reuse = None

    return onezone.register_handle(
        handle_service_id=config.handle_service_id,
        share_id=share_id,
        metadata_xml=dataset.metadata_xml,
        pid_to_reuse=pid_to_reuse,
    )


def _share_public_url(
    share_id: str,
    onezone_domain: str,
    oneprovider: OneproviderClient,
) -> str:
    """Public URL for a share — prefer the recorded one, derive on miss."""
    details = oneprovider.get_share_details(share_id) or {}
    public_url = details.get("publicUrl")
    if public_url:
        return public_url

    return f"https://{onezone_domain}/share/{share_id}"


def _join_paths(*parts: str) -> str:
    """Strip leading/trailing slashes from each part and join with `/`.

    Empty parts drop out, so `_join_paths("", "ds-1") == "ds-1"`.
    """
    cleaned = [p.strip("/") for p in parts if p]
    return "/".join(cleaned)
