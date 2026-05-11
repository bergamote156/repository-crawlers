"""Progress reporting protocol for the registration loop."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from typing import Literal, Protocol

from registrar.register.types import DatasetOutcome


class ProgressSink(Protocol):
    """Abstraction for reporting registration progress to the operator."""

    def start_dataset(self, idx: int, total: int, name: str, file_count: int) -> None: ...
    def advance_phase(self, phase: Literal["files", "share", "record"]) -> None: ...
    def tick_file(self) -> None: ...
    def finish_dataset(self, outcome: DatasetOutcome) -> None: ...


class NullProgressSink:
    """No-op sink for tests and non-interactive runs."""

    def start_dataset(self, idx: int, total: int, name: str, file_count: int) -> None:
        pass

    def advance_phase(self, phase: Literal["files", "share", "record"]) -> None:
        pass

    def tick_file(self) -> None:
        pass

    def finish_dataset(self, outcome: DatasetOutcome) -> None:
        pass
