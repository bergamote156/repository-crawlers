"""
Resolution-time errors raised while loading configuration fields.

Each error class owns a frozen value-record dataclass that pre-computes
its rendering data at raise time. Records carry strings only — no live
schema, source, or `ConfigBase` references — so error objects survive
being passed to logging sinks, structured handlers, or rendered later.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

from confline.errors.base import ConfigError

# ─────────────────────────────────────────────────────────────────────────────
# Source value error
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SourceValueRecord:
    """Pre-computed rendering data for a single source-value failure.

    Self-contained snapshot — once constructed, the renderer can produce
    a complete error message from this record alone. No schema or source
    references are retained.
    """

    path: str
    """Dotted schema path of the field that received the bad value."""

    type_desc: str
    """Human-readable expected type, pre-computed at raise time."""

    secret: bool
    """Whether the field is marked secret; governs value redaction in the renderer."""

    source_label: str | None
    """Operator-facing source provenance (e.g. 'yaml /etc/app.yml').
    None when no source was active (e.g. a field validator raised after
    resolution had already written the value)."""

    source_native_key: str | None
    """Source-native key form pre-computed at raise time (e.g. '--port', 'MYAPP_PORT').
    None when the source cannot name the field or no source is active."""

    value: Any
    """Raw value that failed coercion. Pre-redacted to None for secret fields
    so the record can be safely passed to logs and structured handlers."""

    suggestions: tuple[str, ...]
    """'Try one of' lines pre-computed from the remaining source channels."""


class SourceValueError(ConfigError):
    """A source found a value but it cannot be coerced or is otherwise invalid.

    - `detail` — short failure message used in `str()`.
    - `field_record` — pre-computed rendering data; None for errors raised by
      third-party code that has no schema context.
    """

    _EXIT_CODE: ClassVar[int] = 65  # EX_DATAERR

    def __init__(
        self,
        detail: str,
        *,
        field_record: SourceValueRecord | None = None,
    ) -> None:
        self.detail = detail
        self.field_record = field_record

        ctx = []
        if field_record is not None:
            ctx.append(f"field={field_record.path}")
            if field_record.source_label is not None:
                ctx.append(f"source={field_record.source_label}")

        full = f"{detail} [{', '.join(ctx)}]" if ctx else detail
        super().__init__(full)


# ─────────────────────────────────────────────────────────────────────────────
# Missing required field error
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class MissingFieldRecord:
    """Pre-computed rendering data for one missing required field."""

    path: str
    """Dotted schema path of the missing field."""

    type_desc: str
    """Human-readable expected type, pre-computed at raise time."""

    suggestions: tuple[str, ...]
    """'Try one of' lines pre-computed from the full active source chain."""


class MissingRequiredError(ConfigError):
    """A required field had no value from any source.

    - `fields` — pre-computed records for each missing field, including expected
      type and 'Try one of' suggestions.
    - `sources_tried` — the ordered chain of source names (canonical wire-ids,
      not human labels), used in the fallback string and in the expanded
      CLI template. Names are stable across versions; labels are not.
    """

    _EXIT_CODE: ClassVar[int] = 64  # EX_USAGE

    def __init__(
        self,
        fields: Sequence[MissingFieldRecord],
        *,
        sources_tried: Sequence[str] = (),
    ) -> None:
        self.fields = tuple(fields)
        self.sources_tried = tuple(sources_tried)

        names = [f.path for f in self.fields]
        suffix = (
            f" (sources tried: {', '.join(self.sources_tried)})"
            if self.sources_tried
            else ""
        )
        super().__init__(f"missing required field(s): {', '.join(names)}{suffix}")


# ─────────────────────────────────────────────────────────────────────────────
# Mutex violation error
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ProvidedField:
    """One mutex-conflict provider, fully resolved at raise time.

    Deliberately a value object — stores only strings and an already
    redacted/render-safe value, no live `Source` or `ConfigBase` references.
    """

    path: str
    """Dotted schema path of the provided field."""

    secret: bool
    """When True, the value is already SECRET_PLACEHOLDER — render bare, not repr'd."""

    source_name: str
    """Canonical source identity used to find the active source renderer."""

    source_label: str
    """Human provenance label printed in the error (e.g. 'yaml /etc/app.yml')."""

    source_native_key: str | None
    """Source-native key form (e.g. '--port', 'MYAPP_PORT', 'db.port').
    None causes rendering to fall back to `path` and suppresses the action hint."""

    value: Any
    """Already-redacted value; `secret=True` tells the renderer to print it bare."""


class MutexViolationError(ConfigError):
    """A mutually-exclusive group received the wrong number of providers.

    - `group_name` — kept for programmatic handlers and debugging; the default
      renderer uses `field_paths` instead because group names are often internal.
    - `field_paths` — complete set of option paths in the mutex group; needed
      even when no field was provided so the renderer can list the choices.
    - `provided` — subset that was actually set, as `ProvidedField` records with
      value, source, native key, and removal hint pre-resolved.
    - `required` — selects the "exactly one" versus "at most one" contract.
    """

    _EXIT_CODE: ClassVar[int] = 64  # EX_USAGE

    def __init__(
        self,
        *,
        group_name: str,
        field_paths: Sequence[str],
        provided: Sequence[ProvidedField],
        required: bool,
    ) -> None:
        self.group_name = group_name
        self.field_paths = tuple(field_paths)
        self.provided = tuple(provided)
        self.required = required

        names_str = ", ".join(self.field_paths)
        if required:
            verdict = (
                f"exactly one of [{names_str}] must be set "
                f"(got {len(self.provided)})"
            )
        else:
            verdict = (
                f"at most one of [{names_str}] may be set "
                f"(got {len(self.provided)})"
            )
        super().__init__(verdict)
