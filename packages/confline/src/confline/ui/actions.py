"""
Custom argparse Actions used by the parser builder.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import argparse
from collections.abc import Callable, Sequence
from typing import Any


class HeterogeneousTupleAction(argparse.Action):
    """Per-position parsing for `tuple[X, Y, Z]` annotations.

    Argparse's stock `type=` runs one callable across all positions —
    wrong for heterogeneous tuples. This action accepts a `types`
    keyword (a tuple of per-position parsers) and dispatches.
    """

    def __init__(
        self,
        *args: Any,
        types: tuple[Callable[[str], Any], ...] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._types: tuple[Callable[[str], Any], ...] = types or ()

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        seq = list(values) if isinstance(values, (list, tuple)) else [values]
        if len(seq) != len(self._types):
            raise argparse.ArgumentError(
                self,
                f"expected {len(self._types)} values, got {len(seq)}",
            )
        coerced: list[Any] = []
        for parser_callable, raw in zip(self._types, seq, strict=False):
            try:
                coerced.append(parser_callable(str(raw)))
            except (ValueError, TypeError) as exc:
                raise argparse.ArgumentError(self, str(exc)) from exc
        setattr(namespace, self.dest, tuple(coerced))


class CountAction(argparse.Action):
    """Increments the field on each occurrence (`-vvv` pattern).

    Works under `default=argparse.SUPPRESS`: missing flag → no
    namespace attr, ArgparseSource defers to the next source. Stock
    `action="count"` requires a non-SUPPRESS default and would clash
    with confline's "did the user pass this?" tracking.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("nargs", 0)
        super().__init__(*args, **kwargs)

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        current = getattr(namespace, self.dest, 0) or 0
        setattr(namespace, self.dest, current + 1)
