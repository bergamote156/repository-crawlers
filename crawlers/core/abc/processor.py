"""
Processor Base

Abstract base class for typed processors with statistics tracking.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from crawlers.core.result import Result


@dataclass
class ProcessorStats:
    """
    Base statistics for any processor.

    Subclass to add processor-specific statistics fields.
    Override __str__ for custom formatting.
    """

    processed: int = 0
    filtered: int = 0
    failed: int = 0

    def __str__(self) -> str:
        return f"{self.processed} ok, {self.filtered} filtered, {self.failed} failed"


class Processor[InT, OutT, StatsT: ProcessorStats](ABC):
    """
    Abstract base class for typed processors.

    Processors transform data in a pipeline. Each processor has:
    - Input type I
    - Output type O
    - Lifecycle methods (open/close)
    - Processing method
    - Statistics tracking via stats property
    - Optional enable/disable via `enabled` flag

    Returning Err from process() signals that the item should be
    rejected (not passed to the next processor). The pipeline
    routes Err values to the rejection sink via errors.to_json().

    Example:
        class MyProcessor(Processor[InputDataset, OutputDataset]):

            async def process(self, item: InputDataset) -> Result[OutputDataset, object]:
                if item.title.startswith("Test"):
                    self._stats.filtered += 1
                    return Err({"dataset_id": item.identifier, "reason": "filtered"})

                self._stats.processed += 1
                return Ok(item)
    """

    def __init__(self, enabled: bool = True):
        """
        Initialize processor with statistics.

        Args:
            enabled: Whether this processor is active. Disabled processors
                     are skipped during pipeline execution.
        """
        self._stats = self._create_stats()
        self.enabled = enabled

    def _create_stats(self) -> StatsT:
        """
        Create statistics instance for this processor.

        Override in subclass to return a specific stats class.

        Returns:
            ProcessorStats instance (or subclass)
        """
        return cast(StatsT, ProcessorStats())

    @property
    def stats(self) -> StatsT:
        """Return processor statistics."""
        return self._stats

    def describe(self) -> str:
        """
        Return human-readable description for logging.

        Override in subclass for custom description.
        Default returns class name.

        Returns:
            One-line description of what this processor does
        """
        return self.__class__.__name__

    def artifacts(self) -> list[Path]:
        """
        Return output files/artifacts produced by this processor.

        Override in subclass if processor produces output files.

        Returns:
            List of output file paths (empty by default)
        """
        return []

    async def open(self) -> None:
        """
        Initialize processor resources.

        Called before processing starts. Override to open files,
        create connections, etc.
        """
        return None

    async def close(self) -> None:
        """
        Cleanup processor resources.

        Called after processing ends. Override to close files,
        release connections, etc. Statistics are NOT printed here -
        they are collected and printed at a higher level.
        """
        return None

    @abstractmethod
    async def process(self, item: InT) -> Result[OutT, object]:
        """
        Process a single item.

        Args:
            item: Input item of type InT

        Returns:
            Ok(item) on success, Err(reason) to reject
        """
        raise NotImplementedError
