"""
Builders for resolution-time error records.

Records freeze the rendering data at raise time so error objects survive
being passed to async logging sinks, structured handlers, or rendered
later by `confline.ui.errors`. Builders here own the cross-source "Try
one of" hint generation as well, since suggestions span the same source
chain that the records originate from.

Callers redact secret values *before* handing them to the builder — the
builder is a pure transformation, not a policy layer.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from typing import Any

from confline.config.schema import ConfigFieldInfo
from confline.errors import MissingFieldRecord, SourceValueRecord
from confline.resolution.coerce import describe_field_type, example_value_for
from confline.resolution.context import (
    ResolutionContext,
    is_source_eligible,
    safe_describe_field,
)
from confline.sources.base import Source


def build_source_value_record(
    field: ConfigFieldInfo,
    *,
    raw_value: Any,
    active_source: Source | None,
    source_label: str | None,
    context: ResolutionContext,
) -> SourceValueRecord:
    """Pre-compute the rendering data for a `SourceValueError`.

    Caller redacts `raw_value` to `None` for secret fields. The active
    source (the one that just failed) is excluded from the suggestion
    chain so the renderer doesn't propose the form that just failed.
    """
    native_key = safe_describe_field(active_source, field) if active_source else None
    return SourceValueRecord(
        path=".".join(field.path),
        type_desc=describe_field_type(field),
        secret=field.secret,
        source_label=source_label,
        source_native_key=native_key,
        value=raw_value,
        suggestions=build_suggestion_strings(field, context, skip=active_source),
    )


def build_missing_field_record(
    field: ConfigFieldInfo,
    context: ResolutionContext,
) -> MissingFieldRecord:
    """Pre-compute the rendering data for one missing required field."""
    return MissingFieldRecord(
        path=".".join(field.path),
        type_desc=describe_field_type(field),
        suggestions=build_suggestion_strings(field, context, skip=None),
    )


def build_suggestion_strings(
    field: ConfigFieldInfo,
    context: ResolutionContext,
    *,
    skip: Source | None,
) -> tuple[str, ...]:
    """Compose 'Try one of' lines for every source the field can come from.

    `skip` excludes the active source (the one that just failed) so the
    renderer doesn't suggest the form that just failed. Pass `None` for
    cases like missing-required where no source has tried yet.
    """
    example = example_value_for(field)
    out: list[str] = []
    seen: set[str] = set()

    for source in context.sources:
        if source is skip:
            continue
        if not is_source_eligible(field, source):
            continue

        label = safe_describe_field(source, field)
        if label is None:
            continue

        line = f"  {label}{source.display_kv_separator}{example}"
        if line in seen:
            continue
        seen.add(line)
        out.append(line)

    return tuple(out)
