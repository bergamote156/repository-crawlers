"""
Processor Pipeline

Chains multiple processors into a sequential pipeline.
"""

from typing import Sequence

from ecudo.processors.base import Processor


class ProcessorPipeline[I, O](Processor[I, O]):
    """
    Chains multiple processors into a sequential pipeline.

    Items flow through processors in order. If any processor returns
    None, the pipeline stops for that item (filtered out).

    Note: For type safety, all processors should have compatible
    input/output types. The pipeline's I type should match the first
    processor's input, and O should match the last processor's output.
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
        current = item
        for processor in self.processors:
            current = await processor.process(current)
            if current is None:
                self._filtered += 1
                return None  # Stop pipeline
        self._processed += 1
        return current  # type: ignore

    def get_stats(self) -> dict:
        """
        Aggregate statistics from all processors.

        Returns:
            Dictionary with pipeline stats and per-processor stats
        """
        stats = {
            "pipeline": {
                "processed": self._processed,
                "filtered": self._filtered,
            },
            "processors": {},
        }

        for processor in self.processors:
            name = type(processor).__name__
            if hasattr(processor, "get_stats"):
                stats["processors"][name] = processor.get_stats()

        return stats

    def __len__(self) -> int:
        """Return number of processors in pipeline."""
        return len(self.processors)

    def __repr__(self) -> str:
        """Return string representation."""
        processor_names = [type(p).__name__ for p in self.processors]
        return f"ProcessorPipeline([{', '.join(processor_names)}])"
