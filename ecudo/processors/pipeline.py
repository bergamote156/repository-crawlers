"""
Processor Pipeline

Chains multiple processors into a sequential pipeline.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from typing import Any, Sequence, cast

from ecudo.processors.base import Processor


class ProcessorPipeline[I, O](Processor[I, O]):
    """
    Chains multiple processors into a sequential pipeline.

    Items flow through processors in order. If any processor returns
    None, the pipeline stops for that item (filtered out).

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
    """

    def __init__(self, processors: Sequence[Processor]):
        """
        Initialize pipeline.

        Args:
            processors: Sequence of processors to chain
        """
        self.processors = list(processors)
        self._processed = 0
        self._filtered = 0

    async def open(self) -> None:
        """Open all processors in order."""
        for processor in self.processors:
            await processor.open()

    async def close(self) -> None:
        """Close all processors in order."""
        for processor in self.processors:
            await processor.close()

    async def process(self, item: I) -> O | None:
        """
        Process item through all processors in sequence.

        Args:
            item: Input item

        Returns:
            Final processed item, or None if filtered by any processor
        """
        current: Any = item
        for processor in self.processors:
            current = await processor.process(current)  # type: ignore[arg-type]
            if current is None:
                self._filtered += 1
                return None  # Stop pipeline
        self._processed += 1
        return cast(O, current)

    def __len__(self) -> int:
        """Return number of processors in pipeline."""
        return len(self.processors)

    def __repr__(self) -> str:
        """Return string representation."""
        processor_names = [type(p).__name__ for p in self.processors]
        return f"ProcessorPipeline([{', '.join(processor_names)}])"
