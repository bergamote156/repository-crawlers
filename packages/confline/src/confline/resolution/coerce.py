"""
Value coercion + type-spec registry.

One central registry (`_TYPE_SPECS`) holds the parser, plain-English
description, and example value for every type confline knows how to
coerce. Built-ins seed the registry; `register_type` extends it with
types the app does not own. The same row drives `coerce()` for actual
conversion and `describe_field_type` / `example_value_for` for the
operator-facing copy in error messages and 'Try one of' hints — so
custom types get nice rendering for free, no parallel ladders.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import threading
from collections.abc import Callable, Collection, Mapping
from dataclasses import MISSING, dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import (
    Any,
    Literal,
    Protocol,
    get_args,
    get_origin,
    runtime_checkable,
)
from uuid import UUID

from confline.config.schema import ConfigFieldInfo


# ─────────────────────────────────────────────────────────────────────────────
# Type spec — one row in the registry
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class TypeSpec:
    """Parser + operator-facing copy for one coercible type."""

    parser: Callable[[Any], Any]
    """Receives the raw value (string from env/cli, already-typed from
    yaml, default literal) and returns the coerced value. Must accept
    target-typed inputs as passthrough — the registry is consulted
    unconditionally once the target matches, even when a YAML/Default
    source has already produced a value of the right type."""

    description: str
    """Plain English used in error/help rendering ("integer", "ISO 8601
    datetime")."""

    example: str
    """Sample value rendered in 'Try one of' hints."""


@runtime_checkable
class _ConflineConvert(Protocol):
    """Duck-type for user types that know how to parse themselves from a string.

    Lighter alternative to `register_type` for types under the app's
    control — no registration, just an `__confline_convert__`
    classmethod. Description/example fall back to defaults
    (`__name__` / `<value>`); types that need nicer rendering should
    register a `TypeSpec` instead.
    """

    @classmethod
    def __confline_convert__(cls, raw: str) -> Any: ...


# ─────────────────────────────────────────────────────────────────────────────
# Built-in parsers
# ─────────────────────────────────────────────────────────────────────────────


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off"):
            return False
        raise ValueError(f"cannot interpret {value!r} as bool")
    return bool(value)


def _parse_int(value: Any) -> int:
    # `bool` is a subclass of `int` — silent coercion would let `True`
    # become 1 in places the user clearly meant a number.
    if isinstance(value, bool):
        raise ValueError(f"cannot use bool {value!r} as int")
    return int(value)


def _parse_float(value: Any) -> float:
    return float(value)


def _parse_str(value: Any) -> str:
    return str(value)


def _parse_path(value: Any) -> Path:
    return Path(value)


def _parse_datetime(value: Any) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def _parse_date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _parse_time(value: Any) -> time:
    return value if isinstance(value, time) else time.fromisoformat(str(value))


def _parse_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


# ─────────────────────────────────────────────────────────────────────────────
# Type-spec registry — read-only snapshot, atomic replacement
# ─────────────────────────────────────────────────────────────────────────────


def _build_default_specs() -> dict[type, TypeSpec]:
    return {
        bool:     TypeSpec(_parse_bool,     "true or false",     "true"),
        int:      TypeSpec(_parse_int,      "integer",           "8080"),
        float:    TypeSpec(_parse_float,    "number",            "1.5"),
        str:      TypeSpec(_parse_str,      "string",            "<value>"),
        Path:     TypeSpec(_parse_path,     "path",              "/path/to/file"),
        datetime: TypeSpec(_parse_datetime, "ISO 8601 datetime", "<value>"),
        date:     TypeSpec(_parse_date,     "ISO 8601 date",     "<value>"),
        time:     TypeSpec(_parse_time,     "ISO 8601 time",     "<value>"),
        UUID:     TypeSpec(_parse_uuid,     "UUID",              "<value>"),
    }


# `_TYPE_SPECS` is replaced atomically on every `register_type` call.
# Lookups in `coerce()` read the global once into a local — they see
# a stable snapshot for the duration of the call, no lock needed even
# under free-threaded CPython. The lock serialises *writers* against
# each other so concurrent registrations can't race the snapshot build.
_TYPE_SPECS: Mapping[type, TypeSpec] = MappingProxyType(_build_default_specs())
_TYPE_SPECS_LOCK = threading.Lock()


def register_type(
    target: type,
    parser: Callable[[Any], Any],
    *,
    description: str | None = None,
    example: str | None = None,
) -> None:
    """Register a parser + rendering copy for a type the app does not own.

    Types under the app's control should expose `__confline_convert__`
    instead — no registration needed, but description/example fall
    back to defaults.

    The parser must accept target-typed inputs as passthrough. The
    registry is consulted whenever the field's declared type matches,
    even if a YAML/Default source has already produced a value of the
    correct type. Idiomatic shape:

        def _parse(value):
            if isinstance(value, MyType):
                return value
            return MyType.from_string(str(value))

    `description` lands in error messages ("expected: <description>")
    and `example` in 'Try one of' hints; both fall back to sane
    defaults (`target.__name__` / `<value>`) when omitted.
    """
    global _TYPE_SPECS
    with _TYPE_SPECS_LOCK:
        new = dict(_TYPE_SPECS)
        new[target] = TypeSpec(
            parser=parser,
            description=description or target.__name__,
            example=example or "<value>",
        )
        _TYPE_SPECS = MappingProxyType(new)


# ─────────────────────────────────────────────────────────────────────────────
# Coercion — main dispatch
# ─────────────────────────────────────────────────────────────────────────────


def coerce(value: Any, target: type) -> Any:
    """Coerce `value` to `target`."""
    if value is None:
        return None

    origin = get_origin(target)
    if origin in _CONTAINER_ORIGINS:
        return _coerce_container(value, target)
    if origin is Literal:
        return _coerce_literal(value, get_args(target))

    if not isinstance(target, type):
        return value

    spec = _TYPE_SPECS.get(target)
    if spec is not None:
        return spec.parser(value)

    convert = getattr(target, "__confline_convert__", None)
    if convert is not None and isinstance(value, str):
        return convert(value)

    if issubclass(target, Enum):
        return _coerce_enum(value, target)

    return value


# ─────────────────────────────────────────────────────────────────────────────
# Coercion — special shapes (Enum, Literal, containers)
# ─────────────────────────────────────────────────────────────────────────────


def _coerce_enum(value: Any, enum_cls: type[Enum]) -> Enum:
    if isinstance(value, enum_cls):
        return value
    # Try by-value first (matches YAML `role: admin` for `Role.ADMIN = "admin"`);
    # fall back to by-name for `role: ADMIN` style.
    try:
        return enum_cls(value)
    except (ValueError, KeyError):
        pass
    if isinstance(value, str):
        try:
            return enum_cls[value]
        except KeyError as exc:
            raise ValueError(f"{value!r} is not a valid {enum_cls.__name__}") from exc
    raise ValueError(f"{value!r} is not a valid {enum_cls.__name__}")


def _coerce_literal(value: Any, args: tuple[Any, ...]) -> Any:
    if value in args:
        return value

    # Coerce by inner type when literals are uniformly typed. Mixed-type
    # Literals (`Literal[1, "two"]`) skip the retry — there's no single
    # cast to attempt.
    inner_types = {type(a) for a in args if a is not None}
    if len(inner_types) != 1:
        raise ValueError(f"{value!r} is not in {args}")

    (inner_type,) = inner_types
    try:
        coerced = inner_type(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{value!r} is not in {args}") from exc

    if coerced not in args:
        raise ValueError(f"{value!r} is not in {args}")
    return coerced


_CONTAINER_ORIGINS = {list, tuple, set, frozenset, dict, Mapping}
_VARIADIC_TUPLE_ARITY = 2  # `tuple[X, ...]` has type args (X, Ellipsis)
_DICT_TYPE_ARITY = 2


def _coerce_container(value: Any, target: type) -> Any:
    origin = get_origin(target)
    args = get_args(target)

    if origin is list:
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"expected list, got {type(value).__name__}")
        item_type = args[0] if args else Any
        return [coerce(v, item_type) for v in value]

    if origin in (set, frozenset):
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError(f"expected sequence, got {type(value).__name__}")
        item_type = args[0] if args else Any
        coerced = (coerce(v, item_type) for v in value)
        return origin(coerced)

    if origin is tuple:
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"expected sequence, got {type(value).__name__}")
        if len(args) == _VARIADIC_TUPLE_ARITY and args[1] is Ellipsis:
            item_type = args[0]
            return tuple(coerce(v, item_type) for v in value)
        if len(value) != len(args):
            raise ValueError(f"expected {len(args)} elements, got {len(value)}")
        return tuple(coerce(v, t) for v, t in zip(value, args, strict=False))

    if origin in (dict, Mapping):
        if not isinstance(value, Mapping):
            raise ValueError(f"expected mapping, got {type(value).__name__}")
        if len(args) == _DICT_TYPE_ARITY:
            key_type, val_type = args
        else:
            key_type, val_type = Any, Any
        return {coerce(k, key_type): coerce(v, val_type) for k, v in value.items()}

    return value


# ─────────────────────────────────────────────────────────────────────────────
# Inference helpers — consumed by config/base.py and ui/argparse_builder.py
# ─────────────────────────────────────────────────────────────────────────────


def infer_choices(target: type) -> Collection[Any] | None:
    """Auto-derive choices for `Enum` and `Literal` types."""
    if isinstance(target, type) and issubclass(target, Enum):
        return list(target)
    if get_origin(target) is Literal:
        return list(get_args(target))
    return None


def container_info(target: type) -> tuple[type | None, tuple[Any, ...]]:
    """Return `(container_origin, type_args)` for container annotations.

    Returns `(None, ())` for non-container targets.
    """
    origin = get_origin(target)
    if origin in _CONTAINER_ORIGINS:
        return origin, get_args(target)
    return None, ()


# ─────────────────────────────────────────────────────────────────────────────
# Type description / example — read from the type registry, fall back per-shape
# ─────────────────────────────────────────────────────────────────────────────


def describe_field_type(field: ConfigFieldInfo) -> str:
    """Plain-English rendering of a field's expected type.

    Reads `_TYPE_SPECS` for built-ins and registered types; falls back
    to per-origin / Enum / Literal logic for shape types and to
    `t.__name__` as a last resort.
    """
    t = field.field_type

    if isinstance(t, type):
        spec = _TYPE_SPECS.get(t)
        if spec is not None:
            return spec.description
        if issubclass(t, Enum):
            return "one of: " + ", ".join(m.name for m in t)

    origin = get_origin(t)
    if origin is Literal:
        return "one of: " + ", ".join(repr(m) for m in get_args(t))
    if origin in (list, set, frozenset):
        return f"{origin.__name__} of values"
    if origin is tuple:
        return "tuple of values"
    if origin is dict:
        return "mapping"

    return t.__name__ if isinstance(t, type) else str(t)


def example_value_for(field: ConfigFieldInfo) -> str:
    """Return a concrete example for a field's 'Try one of' hint.

    Uses `field.default` if it is non-secret and non-MISSING; otherwise
    looks up `_TYPE_SPECS` for a per-type placeholder. Secrets always
    render as `<value>` so the example does not double as a demo of
    the real secret form.
    """
    if not field.secret and field.default is not MISSING:
        return repr(field.default)

    t = field.field_type
    if isinstance(t, type):
        spec = _TYPE_SPECS.get(t)
        if spec is not None:
            return spec.example

    return "<value>"
