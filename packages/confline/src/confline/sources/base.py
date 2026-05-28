"""
Source base classes and shared metadata types.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from confline.config.schema import ConfigFieldInfo, ConfigSchema

__all__ = [
    "NO_VALUE",
    "FileOrigin",
    "Source",
]


class _NoValueType:
    """Sentinel singleton for "this source has no value for the field"."""

    _instance: "_NoValueType | None" = None

    def __new__(cls) -> "_NoValueType":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "NO_VALUE"

    def __bool__(self) -> bool:
        return False


NO_VALUE = _NoValueType()


@dataclass(frozen=True, slots=True)
class FileOrigin:
    """One on-disk config file and the channel that selected it."""

    path: Path
    """Absolute path to the config file."""

    origin: str | None = None
    """Short free-form label such as `"cli"`, `"env"`, or `"explicit"`
    — display metadata for operator-facing diagnostics, not part of
    source identity or resolution."""


class Source(ABC):
    """Base class for config value sources.

    A source resolves one field at a time. It returns a raw value, or
    `NO_VALUE` to defer to the next source. Found-but-invalid values
    should raise `SourceValueError`; resolution must not silently fall
    through after a value was found.
    """

    name: ClassVar[str]
    """Stable wire-id for dispatch and provenance keys.

    Used as a dict key in source registries, in mutex enforcement,
    in ops logs, and as the `Provenance.name` field. Never shown to
    operators directly — for that, use `display_label`.
    """

    display_label: ClassVar[str]
    """Operator-facing label for the source.

    Use for help text, error rendering fallbacks, and any place the
    source is named to a human without instance-specific detail. For
    per-field rendering with file paths, profile names, or
    secret-manager namespaces, override `describe_provenance(field)`.
    """

    display_kv_separator: ClassVar[str] = " "
    """Source-native separator between key and value.

    Built-ins: argparse `" "`, env `"="`, yaml `": "`. Renderers
    compose `f"{key}{display_kv_separator}{value}"` to get a
    source-shaped line — `--port 8080`, `PORT=8080`, `port: 8080`.
    """

    display_in_help_block: ClassVar[bool] = True
    """Whether this source contributes a `{display_label}: {key}` line
    under each field in `--help`. Defaults to True so plugin authors
    get visibility for free; argparse sets False because the flag is
    already in the action header."""

    is_fallback: ClassVar[bool] = False
    """Mark this source as a fallback (declared defaults, baked-in
    constants, …). Values from fallback sources don't count as
    "user-provided" for cross-source mutex enforcement: a YAML file
    setting two mutex-grouped fields conflicts, a `DefaultSource`
    filling them does not. Default is False; `DefaultSource` flips
    it on. Third-party fallback sources (Vault default, baseline
    config) opt in by overriding the flag."""

    def validate_schema(self, schema: ConfigSchema) -> None:  # noqa: ARG002 — default no-op
        """Validate source-specific schema constraints before resolution.

        Sources that project fields into an external namespace can use
        this hook to catch naming collisions early. The default is a
        no-op.
        """
        return None

    @classmethod
    def supports_field(cls, field: ConfigFieldInfo) -> bool:  # noqa: ARG003 — default no-op
        """Return False if this source cannot represent the field's shape.

        Distinct from `excluded_from` — that's an explicit user-side
        opt-out per field. `supports_field` is a source-side capability
        check: argparse and env vars cannot express `list[ConfigBase]`,
        so they self-skip those fields without the user having to
        annotate every one. Default is True (source can resolve any
        field shape); override on subclasses that have shape limits.
        """
        return True

    @abstractmethod
    def resolve(self, field: ConfigFieldInfo) -> Any:
        """Return this field's raw value or `NO_VALUE`."""

    def describe_field(self, field: ConfigFieldInfo) -> str | None:
        """Return the source-native key for this field.

        Examples: `--port`, `MYAPP_PORT`, `db.port`. Returns `None`
        when the source has no key form for the field or the field is
        excluded from this source. Override `_describe_field()` in
        subclasses; this public method keeps `excluded_from` behavior
        consistent across help and error rendering.
        """
        if type(self) in field.excluded_from:
            return None

        return self._describe_field(field)

    def _describe_field(self, field: ConfigFieldInfo) -> str | None:  # noqa: ARG002 — default no-op
        """Return this source's key label for `field`."""
        return None

    def describe_provenance(self, field: ConfigFieldInfo) -> str | None:  # noqa: ARG002 — default no-op
        """Return an instance-level label for per-field provenance.

        Returns `None` to let the renderer fall back to `display_label`.
        Override when an instance can add useful context, such as a
        YAML file path, a profile name, or a secret-manager namespace.
        """
        return None

    def describe_unset_hint(self, key: str) -> str | None:  # noqa: ARG002 — default no-op
        """Return the imperative suffix telling the operator how to
        unset the key — used in mutex conflict messages.

        Built-ins use forms such as ` — unset MYAPP_PORT`,
        ` — remove --port`, ` — remove db.host`. Return `None` to
        suppress the suffix.
        """
        return None
