"""
Result type for explicit error handling.

Provides Ok[T] and Err[E] types as an alternative to returning None or empty dicts
on failure. Inspired by Erlang's {ok, Val} | {error, Reason}.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from collections.abc import Callable
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# JSON (RFC 8259) value tree.
#
# Nested `dict` / `list` use `Any` so values like `list[str]` (e.g. STAC
# `collections`) type-check; fully recursive `list[JsonValue]` is invariant
# and fights mypy on normal API payloads.
# ─────────────────────────────────────────────────────────────────────────────

type JsonValue = str | int | float | bool | None | dict[str, Any] | list[Any]
type JsonObject = dict[str, Any]


# ─────────────────────────────────────────────────────────────────────────────
# Result type.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Ok[T]:
    """Successful outcome wrapping a value of type `T`."""

    value: T

    def map[U](self, fn: Callable[[T], U]) -> "Ok[U]":
        """Apply `fn` to the wrapped value and return a new `Ok`.

        Args:
            fn: Function mapping the success value to a new type.

        Returns:
            `Ok` containing `fn(self.value)`.
        """
        return Ok(fn(self.value))


@dataclass(frozen=True, slots=True)
class Err[E]:
    """Failed outcome wrapping an error value of type `E`."""

    value: E

    def map(self, _fn: Callable) -> "Err[E]":
        """Return `self` unchanged; mapping does not apply to errors.

        Args:
            _fn: Ignored; present for a uniform `Result` map API with `Ok.map`.

        Returns:
            This `Err` instance.
        """
        return self


type Result[T, E] = Ok[T] | Err[E]


def failure_to_json(failure: Any) -> dict:
    """Serialize any failure to a JSON-safe dict.

    Supports:
    - dict: returned as-is
    - objects with to_json(): call it
    - dataclass instances: `asdict()` (nested dataclasses become nested dicts)
    - anything else: wrap in {"error": str(err)}
    """
    if isinstance(failure, dict):
        return failure
    if hasattr(failure, "to_json"):
        as_json: dict = failure.to_json()
        return as_json
    if is_dataclass(failure) and not isinstance(failure, type):
        return asdict(failure)

    return {"failure": str(failure)}
