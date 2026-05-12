"""
Confline configuration classes for the registrar CLI.

Three logical layers:

- `CommonConfig` — connection/auth/output/logging shared by every command.
- Per-command configs — `RegisterConfig`, `ListSpacesConfig`,
  `ListStoragesConfig` — extend `CommonConfig` with command-specific fields.
- Mutex groups — `SpaceSelection`, `StorageSelection` — encode the
  name-or-ID alternatives so confline auto-renders "at most one of …" errors.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from pathlib import Path
from typing import Annotated, Literal

from confline import (
    ConfigBase,
    MutuallyExclusiveGroup,
    model_validator,
    opt,
)
from confline.sources import CliPositional

# ─────────────────────────────────────────────────────────────────────────────
# Shared sub-configs
# ─────────────────────────────────────────────────────────────────────────────


class OnedataConnection(ConfigBase):
    """Connection settings for Onedata services."""

    onezone_domain: str = opt(
        "demo.onedata.org",
        description="Onezone domain used for space and public-data-record operations.",
    )
    oneprovider_domain: str = opt(
        "provider.demo.onedata.org",
        description="Oneprovider domain used for data and Onepanel admin operations.",
    )
    oneprovider_panel_port: int = opt(
        443,
        description="Onepanel HTTPS API port on the selected Oneprovider.",
    )
    verify_ssl: bool = opt(
        False,
        description="Verify TLS certificates when talking to Onedata services.",
    )


class Tokens(ConfigBase):
    """Authentication tokens for Onedata APIs."""

    admin_token: str = opt(
        "",
        description="Onepanel admin token (storage management, space support).",
        secret=True,
    )
    space_owner_token: str = opt(
        "",
        description="User token (space creation, file registration, shares, handles).",
        secret=True,
    )


class Output(ConfigBase):
    """Output and report destinations for `register`."""

    dir: Path = opt(
        Path("./data"),
        description="Directory for run artifacts (logs, config dump, summary).",
    )


class Logging(ConfigBase):
    """Logging verbosity. `quiet` and `verbose` are convenience overrides of `level`."""

    level: Literal["debug", "info", "warning", "error", "silent"] = opt(
        "info",
        description="Explicit logging level.",
    )
    quiet: bool = opt(
        False,
        description="Show warnings, errors, and the final summary only.",
    )
    verbose: bool = opt(
        False,
        description="Show debug-level output.",
    )


class CommonConfig(ConfigBase):
    """Settings shared by every command."""

    onedata: OnedataConnection = opt(default_factory=OnedataConnection)
    tokens: Tokens = opt(default_factory=Tokens)
    logging: Logging = opt(default_factory=Logging)


# ─────────────────────────────────────────────────────────────────────────────
# Mutex groups for register
# ─────────────────────────────────────────────────────────────────────────────


class SpaceSelection(MutuallyExclusiveGroup, required=False):
    """Pick the target space — by name (use-or-create) or by ID (use-existing)."""

    name: str = opt(
        "",
        description="Use or create a space with this exact name.",
    )
    id: str = opt(
        "",
        description="Use a specific existing space by its ID.",
    )


class StorageSelection(MutuallyExclusiveGroup, required=False):
    """Pick the storage backing the space."""

    name: str = opt(
        "",
        description="Use or create an HTTP readonly storage with this exact name.",
    )
    id: str = opt(
        "",
        description="Use a specific existing storage by its ID.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public-data-records / sharing
# ─────────────────────────────────────────────────────────────────────────────


class PublicDataRecords(ConfigBase):
    """Sharing and public-data-record policy applied to every dataset."""

    enabled: bool = opt(
        True,
        description=(
            "Create or reuse a public data record per dataset share. "
            "Set false to create only the share and skip records/handles."
        ),
    )
    handle_service_id: str = opt(
        "",
        description="Handle service ID. Required when `register` is true.",
    )
    public_identifier_type: Literal["onedata-url", "pid"] = opt(
        "onedata-url",
        description=(
            "Identifier kind to mint when a new identifier is needed. "
            "`onedata-url` registers the handle without requesting a public "
            "handle; `pid` requests one from the configured handle service."
        ),
    )
    identifier_policy: Literal[
        "always-generate-new",
        "always-reuse-existing",
        "generate-new-if-missing",
    ] = opt(
        "generate-new-if-missing",
        description=(
            "How to treat the per-dataset `pid` from the input. "
            "`always-generate-new` ignores input PIDs; "
            "`always-reuse-existing` requires every dataset to provide one; "
            "`generate-new-if-missing` reuses when present, mints otherwise."
        ),
    )

    @model_validator
    def _handle_service_requires_id(self):
        if self.enabled and not self.handle_service_id:
            raise ValueError(
                "enabled=true requires public_data_records.handle_service_id.",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Per-command configs
# ─────────────────────────────────────────────────────────────────────────────


class RegisterConfig(CommonConfig):
    """Configuration for `registrar register`."""

    output: Output = opt(default_factory=Output)
    datasets_file: Annotated[Path, CliPositional] = opt(
        description="Path to the JSON or JSONL file with the datasets to register.",
    )
    space: SpaceSelection = opt(default_factory=SpaceSelection)
    storage: StorageSelection = opt(default_factory=StorageSelection)
    storage_endpoint: str = opt(
        "",
        description=(
            "Endpoint URL used when the registrar creates a new HTTP storage. "
            "If omitted, inferred from the first file URL in the input."
        ),
    )
    storage_default_size: int = opt(
        1099511627776,  # 1 TiB
        description=(
            "Default support size in bytes used when this run adds storage support "
            "for the resolved space."
        ),
    )
    dataset_root: str = opt(
        "",
        description=(
            "Relative path inside the space where dataset directories will be created. "
            "Empty means each dataset's `target_dir` is the top-level directory."
        ),
    )
    yes: bool = opt(
        False,
        description=(
            "Accept a deterministic plan without prompting. "
            "Refuses to auto-resolve any ambiguity even when set."
        ),
    )
    public_data_records: PublicDataRecords = opt(default_factory=PublicDataRecords)


class ListSpacesConfig(CommonConfig):
    """Configuration for `registrar list-spaces`."""


class ListStoragesConfig(CommonConfig):
    """Configuration for `registrar list-storages`."""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def effective_log_level(logging: Logging) -> str:
    """Resolve `quiet` / `verbose` convenience flags into a concrete level.

    `verbose` wins over `quiet` (matches the legacy CLI). When neither is
    set, the explicit `level` field is returned unchanged.
    """
    if logging.verbose:
        return "debug"
    if logging.quiet:
        return "warning"
    return logging.level
