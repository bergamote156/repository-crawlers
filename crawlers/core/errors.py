"""
Structured error types for Result[T, E].

Designed for pattern matching:

    match result:
        case Err(HttpError(status=404)):
            ...
        case Err(TimeoutError(url=url)):
            ...
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class HttpError:
    """Non-200 HTTP response."""

    status: int
    method: str
    url: str
    body: str = ""

    def to_json(self) -> dict:
        """Serialize to a JSON-safe dict."""
        return {"type": "http_error", **asdict(self)}

    def __str__(self) -> str:
        return f"HTTP {self.status} {self.method} {self.url}"


@dataclass(frozen=True)
class HttpTimeoutError:
    """All retry attempts exhausted due to network/timeout errors."""

    method: str
    url: str
    attempts: int
    last_error: str

    def to_json(self) -> dict:
        """Serialize to a JSON-safe dict."""
        return {"type": "timeout_error", **asdict(self)}

    def __str__(self) -> str:
        return f"Timeout after {self.attempts} attempts: {self.method} {self.url}"


type ApiError = HttpError | HttpTimeoutError


class MatchError(TypeError):
    """Exhaustive match failed — unexpected variant."""

    def __init__(self, value: object) -> None:
        super().__init__(f"Non-exhaustive match: {value!r}")


def to_json(err: object) -> dict:
    """Serialize any error to a JSON-safe dict.

    Supports:
    - dict: returned as-is
    - objects with to_json(): call it
    - anything else: wrap in {"error": str(err)}
    """
    if isinstance(err, dict):
        return err
    if hasattr(err, "to_json"):
        return err.to_json()
    return {"error": str(err)}
