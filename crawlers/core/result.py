"""
Result type for explicit error handling.

Provides Ok[T] and Err[E] types as an alternative to returning
None or empty dicts on failure. Inspired by Erlang's {ok, Val} | {error, Reason}.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, Never


class Result[T, E](ABC):
    """
    Base result type. Never instantiate directly — use Ok() or Err().

    Supports pattern matching:

        match await client.get_json(url):
            case Ok(val):
                process(val)
            case Err(err):
                log(err)
    """

    @abstractmethod
    def is_ok(self) -> bool:
        """Return True if this is Ok."""

    @abstractmethod
    def is_err(self) -> bool:
        """Return True if this is Err."""

    @abstractmethod
    def unwrap(self) -> T:
        """Return value if Ok, raise ValueError if Err."""

    @abstractmethod
    def unwrap_or(self, default: T) -> T:
        """Return value if Ok, otherwise return default."""

    @abstractmethod
    def err(self) -> E:
        """Return error if Err, raise ValueError if Ok."""

    @abstractmethod
    def map[U](self, fn: Callable[[T], U]) -> "Result[U, E]":
        """Apply fn to the value if Ok, pass through if Err."""


class Ok[T](Result[T, Any]):
    """Success variant holding a value."""

    __match_args__ = ("value",)
    __slots__ = ("value",)

    def __init__(self, val: T) -> None:
        self.value = val

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def unwrap(self) -> T:
        return self.value

    def unwrap_or(self, default: T) -> T:
        return self.value

    def err(self) -> Never:
        raise ValueError(f"Called err() on Ok({self.value!r})")

    def map[U](self, fn: Callable[[T], U]) -> "Ok[U]":
        return Ok(fn(self.value))

    def __repr__(self) -> str:
        return f"Ok({self.value!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Ok):
            return NotImplemented
        return self.value == other.value

    def __hash__(self) -> int:
        return hash(("Ok", self.value))


class Err[E](Result[Any, E]):
    """Error variant holding an error reason."""

    __match_args__ = ("value",)
    __slots__ = ("value",)

    def __init__(self, val: E) -> None:
        self.value = val

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def unwrap(self) -> Never:
        raise ValueError(f"Called unwrap() on Err({self.value!r})")

    def unwrap_or[T](self, default: T) -> T:
        return default

    def err(self) -> E:
        return self.value

    def map(self, fn: Callable) -> "Err[E]":
        return self

    def __repr__(self) -> str:
        return f"Err({self.value!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Err):
            return NotImplemented
        return self.value == other.value

    def __hash__(self) -> int:
        return hash(("Err", self.value))
