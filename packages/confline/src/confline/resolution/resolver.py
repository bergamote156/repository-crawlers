"""
Schema → instance resolver.

Walks the schema, queries sources in order, coerces and validates each
value, attaches per-field provenance to the returned instance.

Errors are typed: `MissingRequiredError`, `SourceValueError`, and
`MutexViolationError` — each carrying pre-computed render data (see
`confline.resolution.error_records`) so they can be serialised to logs
or rendered later by `confline.ui.errors`.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import dataclasses
from collections.abc import Sequence
from typing import Any, NamedTuple, NoReturn

from confline.config.base import ConfigBase
from confline.config.schema import ConfigFieldInfo, ConfigSchema
from confline.config.types import SECRET_PLACEHOLDER, FieldPath, Provenance
from confline.errors import (
    ConfigError,
    MissingFieldRecord,
    MissingRequiredError,
    SourceValueError,
)
from confline.resolution.coerce import coerce
from confline.resolution.context import (
    ResolutionContext,
    is_source_eligible,
    safe_describe_provenance,
)
from confline.resolution.error_records import (
    build_missing_field_record,
    build_source_value_record,
)
from confline.resolution.mutex import enforce_mutex_groups
from confline.sources.base import NO_VALUE, Source

_UNRESOLVED = object()
"""Sentinel — `_resolve_field` returns this in `value` when no source
produced a non-`NO_VALUE` for the field. Distinct from `dataclasses.MISSING`
(no declared default) and from `NO_VALUE` (this source skipped this field)."""


class _ResolvedField(NamedTuple):
    """Resolved scalar value and source metadata."""

    value: Any
    """Coerced value, or the `_UNRESOLVED` sentinel when no source
    produced a value. In the unresolved case `source_name` and
    `source_label` carry no meaning."""

    source_name: str
    """Canonical wire-id of the producing source."""

    source_label: str
    """Operator-facing source label, possibly per-instance
    (e.g. `"yaml /etc/app.yml"`)."""


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────


def load_config(
    config_class: type[ConfigBase],
    *,
    sources: Sequence[Source],
) -> ConfigBase:
    """Resolve `config_class` against `sources` and return an instance.

    Sources are queried in order; the first non-`NO_VALUE` wins.
    Per-field provenance is stashed on the returned instance and surfaced
    by `ConfigBase.source_of(path) -> Provenance` — the same data backs
    the public read and the post-resolution mutex enforcement.
    """
    schema = config_class.__config_schema__
    context = ResolutionContext(sources=tuple(sources))
    for source in context.sources:
        source.validate_schema(schema)

    provenance: dict[FieldPath, Provenance] = {}
    instance = _resolve_schema(
        schema, prefix=(), context=context, provenance=provenance,
    )
    instance._attach_provenance(provenance)
    enforce_mutex_groups(instance, provenance, context)
    return instance


# ─────────────────────────────────────────────────────────────────────────────
# Schema / field traversal
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_schema(
    schema: ConfigSchema,
    *,
    prefix: FieldPath,
    context: ResolutionContext,
    provenance: dict[FieldPath, Provenance],
) -> ConfigBase:
    init_kwargs: dict[str, Any] = {}
    missing_required: list[MissingFieldRecord] = []

    for field in schema.all_fields():
        full_path = prefix + field.path

        if field.nested_schema is not None:
            init_kwargs[field.name] = _resolve_schema(
                field.nested_schema,
                prefix=full_path,
                context=context,
                provenance=provenance,
            )
            continue

        view = dataclasses.replace(field, path=full_path)
        resolved = _resolve_field(view, context)

        if resolved.value is _UNRESOLVED:
            # No source returned a value. Required field → typed
            # error naming the field and the source chain; the
            # dataclass `__init__` would otherwise raise a context-
            # free TypeError.
            if not field.has_default:
                missing_required.append(build_missing_field_record(view, context))
            continue

        provenance[full_path] = Provenance(
            name=resolved.source_name,
            label=resolved.source_label,
        )
        init_kwargs[field.name] = resolved.value

    if missing_required:
        raise MissingRequiredError(
            missing_required,
            sources_tried=tuple(s.name for s in context.sources),
        )

    instance = schema.config_class(**init_kwargs)
    _run_validators(instance, schema, context)
    return instance


def _resolve_field(
    field: ConfigFieldInfo,
    context: ResolutionContext,
) -> _ResolvedField:
    """Walk sources in order; first non-NO_VALUE wins. Coerce + run opt validator.

    Returns value + source identity metadata. `source_name` is
    canonical identity (mutex enforcement); `source_label` is
    human-facing (error rendering).
    """
    for source in context.sources:
        if not is_source_eligible(field, source):
            continue

        raw = _resolve_raw_value(field, source, context)
        if raw is NO_VALUE:
            continue

        prov_label = safe_describe_provenance(source, field)
        value = _coerce_field_value(
            field, source, raw, source_label=prov_label, context=context,
        )
        value = _run_optional_validator(
            field, source, value, source_label=prov_label, context=context,
        )
        return _ResolvedField(value=value, source_name=source.name, source_label=prov_label)

    return _ResolvedField(value=_UNRESOLVED, source_name="", source_label="")


# ─────────────────────────────────────────────────────────────────────────────
# Per-field stages
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_raw_value(
    field: ConfigFieldInfo,
    source: Source,
    context: ResolutionContext,
) -> Any:
    """Call `source.resolve(field)` and translate unexpected failures."""
    try:
        return source.resolve(field)
    except ConfigError:
        # Typed framework errors propagate with their own context —
        # reframing would lose the field-level message.
        raise
    except Exception as exc:  # noqa: BLE001 — translate any source bug
        # Catches default_factory raises, third-party Vault timeouts,
        # custom-source bugs. Without this, the user sees a context-
        # free traceback into the source's internals.
        _raise_source_value_error(
            exc,
            field=field,
            raw_value=None,
            active_source=source,
            source_label=source.display_label,
            context=context,
        )


def _coerce_field_value(
    field: ConfigFieldInfo,
    source: Source,
    raw: Any,
    *,
    source_label: str,
    context: ResolutionContext,
) -> Any:
    """Apply count/null guards and coerce raw to the field type."""
    if field.is_count and isinstance(raw, bool):
        _raise_source_value_error(
            ValueError("cannot use boolean for a count field"),
            field=field,
            raw_value=raw,
            active_source=source,
            source_label=source_label,
            context=context,
        )

    if raw is None:
        if not _accepts_none(field):
            _raise_source_value_error(
                ValueError("explicit null not allowed for non-Optional field"),
                field=field,
                raw_value=raw,
                active_source=source,
                source_label=source_label,
                context=context,
            )
        return None

    try:
        return coerce(raw, field.field_type)
    except (ValueError, TypeError) as exc:
        _raise_source_value_error(
            exc,
            field=field,
            raw_value=raw,
            active_source=source,
            source_label=source_label,
            context=context,
        )


def _run_optional_validator(
    field: ConfigFieldInfo,
    source: Source,
    value: Any,
    *,
    source_label: str,
    context: ResolutionContext,
) -> Any:
    """Run `opt(validator=...)` when configured; otherwise return input value."""
    if field.validator is None:
        return value

    try:
        return field.validator(value)
    except (ValueError, TypeError) as exc:
        _raise_source_value_error(
            exc,
            field=field,
            raw_value=value,
            active_source=source,
            source_label=source_label,
            context=context,
        )


def _accepts_none(field: ConfigFieldInfo) -> bool:
    """True when an explicit `None` is a legal resolved value.

    Optional fields obviously accept None; bare `Any` does too. Anything
    else gets a SourceValueError instead of letting the dataclass __init__
    surface a context-free TypeError.
    """
    if field.is_optional:
        return True

    return field.field_type is Any or field.field_type is type(None)


# ─────────────────────────────────────────────────────────────────────────────
# Post-construction validators
# ─────────────────────────────────────────────────────────────────────────────


def _run_validators(
    instance: ConfigBase,
    schema: ConfigSchema,
    context: ResolutionContext,
) -> None:
    """Fire `@field_validator` and `@model_validator` methods.

    NOTE: nested `ConfigBase` has already been validated by the
    recursive `_resolve_schema` call. Here we run validators for
    `instance` itself: field-scoped first, then model-level in
    declaration order.
    """
    for field_name, method_names in schema.field_validators.items():
        field = schema.find_field(field_name)
        for method_name in method_names:
            current = getattr(instance, field_name)

            try:
                new_value = getattr(instance, method_name)(current)
            except ConfigError:
                # Already a typed framework error — propagate with
                # its own context. Re-wrapping would lose the
                # field-level message validators bothered to write.
                raise
            except Exception as exc:  # noqa: BLE001 — user-code translation
                if field is None:
                    # `@field_validator("name")` referenced a name not
                    # in the schema (typo in user code). Surface the
                    # bare message; no field metadata to enrich the
                    # record with.
                    raise SourceValueError(str(exc)) from exc
                _raise_source_value_error(
                    exc, field=field, raw_value=current, context=context,
                )

            setattr(instance, field_name, new_value)

    for method_name in schema.model_validators:
        # Model validators bubble bare: callers like
        # `@model_validator raise ValueError("username and password must
        # be set together")` are documented to surface ValueError unchanged.
        getattr(instance, method_name)()


# ─────────────────────────────────────────────────────────────────────────────
# Error wrapping
# ─────────────────────────────────────────────────────────────────────────────


def _raise_source_value_error(
    exc: Exception,
    *,
    field: ConfigFieldInfo,
    raw_value: Any,
    context: ResolutionContext,
    active_source: Source | None = None,
    source_label: str | None = None,
) -> NoReturn:
    """Wrap an underlying coerce/validator exception into `SourceValueError`.

    Secret fields get both the wrapper message and the chained
    `__cause__` scrubbed of the raw value, so structured logging
    frameworks that walk `__cause__` cannot pick the secret out of
    the original `ValueError`.

    Record assembly (suggestions, type description, source-native key)
    is delegated to `error_records.build_source_value_record`.
    """
    if field.secret:
        cause: Exception = type(exc)(f"<{type(exc).__name__}: value redacted>")
        message = f"could not coerce value (redacted, was {SECRET_PLACEHOLDER})"
        record_value: Any = None
    else:
        cause = exc
        message = str(exc)
        record_value = raw_value

    record = build_source_value_record(
        field,
        raw_value=record_value,
        active_source=active_source,
        source_label=source_label,
        context=context,
    )
    raise SourceValueError(message, field_record=record) from cause
