"""
Processor Pipeline

Chains multiple processors into a sequential pipeline.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from pathlib import Path
from typing import Any, Sequence, cast

from crawlers.core.abc.processor import Processor, ProcessorStats


class ProcessorPipeline[InT, OutT](Processor[InT, OutT, ProcessorStats]):
    """
    Chains multiple processors into a sequential pipeline.

    Items flow through processors in order. If any processor returns
    None, the pipeline stops for that item (filtered out).

    Statistics are tracked by individual processors - use get_processor_stats()
    to collect them.

    Note: For type safety, all processors should have compatible
    input/output types. The pipeline's I type should match the first
    processor's input, and O should match the last processor's output.

    Example usage:
        pipeline = ProcessorPipeline([
            DatasetFetcher(...),
            URLValidator(...),
            OnedataConverter(...),
            JSONLWriter(...),
        ])

        await pipeline.open()
        result = await pipeline.process(record_id)  # Flows through all processors
        await pipeline.close()

        # Get stats from all processors
        for name, stats in pipeline.get_processor_stats():
            print(f"{name}: {stats}")
    """

    def __init__(self, processors: Sequence[Processor]):
        """
        Initialize pipeline.

        Args:
            processors: Sequence of processors to chain
        """
        super().__init__()
        self.processors = list(processors)

    def get_processor_info(self) -> list[tuple[str, str, bool]]:
        """
        Get processor information for display.

        Returns:
            List of (class_name, description, enabled) tuples
        """
        return [(type(p).__name__, p.describe(), p.enabled) for p in self.processors]

    def get_processor_stats(self) -> list[tuple[str, ProcessorStats]]:
        """
        Collect statistics from all enabled processors.

        Returns:
            List of (processor_name, stats) tuples
        """
        return [(type(p).__name__, p.stats) for p in self.processors if p.enabled]

    def get_artifacts(self) -> list[Path]:
        """
        Collect all output files from enabled processors.

        Returns:
            List of output file paths
        """
        artifacts: list[Path] = []
        for processor in self.processors:
            if processor.enabled:
                artifacts.extend(processor.artifacts())
        return artifacts

    async def open(self) -> None:
        """Open all enabled processors in order."""
        for processor in self.processors:
            if processor.enabled:
                await processor.open()

    async def close(self) -> None:
        """Close all enabled processors in order."""
        for processor in self.processors:
            if processor.enabled:
                await processor.close()

    async def process(self, item: InT) -> OutT | None:
        """
        Process item through all enabled processors in sequence.

        Disabled processors are skipped. Each processor is responsible
        for updating its own statistics.

        Args:
            item: Input item

        Returns:
            Final processed item, or None if filtered by any processor
        """
        current: Any = item
        for processor in self.processors:
            if not processor.enabled:
                continue
            current = await processor.process(current)  # type: ignore[arg-type]
            if current is None:
                return None  # Stop pipeline - processor already tracked filtered
        return cast(OutT, current)

    def __len__(self) -> int:
        """Return number of processors in pipeline."""
        return len(self.processors)

    def __repr__(self) -> str:
        """Return string representation."""
        processor_names = [type(p).__name__ for p in self.processors]
        return f"ProcessorPipeline([{', '.join(processor_names)}])"
