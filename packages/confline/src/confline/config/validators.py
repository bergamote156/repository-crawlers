"""
Validator decorators and collection helpers.

Two layers:

- `@model_validator` — class-level method that runs once after the
  instance is fully constructed. Receives `self`; can mutate fields,
  cross-check siblings, raise to abort.
- `@field_validator(*field_names)` — class-level method scoped to
  one or more fields. Runs after the instance exists with the resolved
  value passed in; returns the (possibly transformed) value.

Per-field validators declared via `opt(validator=fn)` are a separate
concern — they live on the field's metadata and run during resolution
(before the instance exists). The two complement each other: `opt()`
validators for stateless transforms, `@field_validator` when the
check needs `self`.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from collections.abc import Callable
from typing import Any, Final

_MODEL_VALIDATOR_FLAG: Final[str] = "__confline_model_validator__"
_FIELD_VALIDATOR_FLAG: Final[str] = "__confline_field_validator__"


def model_validator(method: Callable[..., Any]) -> Callable[..., Any]:
    """Mark a method as a model-level validator.

    Fires after every field of the instance has been resolved.
    Runs in method-declaration order across the MRO (base classes
    first, most-derived last; later definitions of the same method
    name override earlier ones via normal attribute lookup).
    """
    setattr(method, _MODEL_VALIDATOR_FLAG, True)
    return method


def field_validator(*field_names: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark a method as a field-level validator scoped to `field_names`.

    The method is invoked once per named field after instance
    construction, with the resolved value as its second argument.
    The return value replaces the field's value.

    NOTE: String references are not refactor-safe.
    """

    def decorator(method: Callable[..., Any]) -> Callable[..., Any]:
        setattr(method, _FIELD_VALIDATOR_FLAG, tuple(field_names))
        return method

    return decorator


def collect_model_validators(cls: type) -> tuple[str, ...]:
    """Return the method names of `@model_validator` methods.

    Walks the MRO base-to-derived. The first occurrence of a method
    name wins ordering-wise (subsequent overrides keep the position).
    Most-derived implementation fires at runtime via `getattr`.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for klass in reversed(cls.__mro__):
        if klass is object:
            continue

        for name, attr in vars(klass).items():
            if name in seen:
                continue

            if callable(attr) and getattr(attr, _MODEL_VALIDATOR_FLAG, False):
                seen.add(name)
                ordered.append(name)

    return tuple(ordered)


def collect_field_validators(cls: type) -> dict[str, tuple[str, ...]]:
    """Return `{field_name: (method_name, ...)}` for `@field_validator` methods.

    Walks the MRO base-to-derived. Within a field, validator methods
    appear in declaration order across classes.
    """
    result: dict[str, list[str]] = {}
    seen_per_field: dict[str, set[str]] = {}

    for klass in reversed(cls.__mro__):
        if klass is object:
            continue

        for name, attr in vars(klass).items():
            field_names = getattr(attr, _FIELD_VALIDATOR_FLAG, None)
            if field_names is None:
                continue

            for field in field_names:
                bucket = result.setdefault(field, [])
                seen = seen_per_field.setdefault(field, set())
                if name in seen:
                    continue
                seen.add(name)
                bucket.append(name)

    return {field: tuple(methods) for field, methods in result.items()}
