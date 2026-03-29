"""
Processor Pipeline

Chains multiple processors into a sequential pipeline.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from pathlib import Path
from typing import Any, Sequence, cast

from crawlers.core import errors
from crawlers.core.abc.processor import Processor, ProcessorStats
from crawlers.core.result import Err, Ok, Result
from crawlers.core.sinks import Sink


class ProcessorPipeline[InT, OutT](Processor[InT, OutT, ProcessorStats]):
    """
    Chains multiple processors into a sequential pipeline.

    Items flow through processors in order. If any processor returns
    Err, the pipeline stops for that item and pushes the error to
    the rejection sink.

    Statistics are tracked by individual processors - use get_processor_stats()
    to collect them.

    Note: For type safety, all processors should have compatible
    input/output types. The pipeline's I type should match the first
    processor's input, and O should match the last processor's output.

    Example usage:
        pipeline = ProcessorPipeline(
            processors=[
                DatasetFetcher(...),
                URLValidator(...),
                Tap(raw_sink),
                OnedataConverter(...),
                Tap(processed_sink),
            ],
            rejection_sink=ctx.rejection_sink,
        )

        await pipeline.open()
        result = await pipeline.process(record_id)  # Flows through all processors
        await pipeline.close()

        # Get stats from all processors
        for name, stats in pipeline.get_processor_stats():
            print(f"{name}: {stats}")
    """

    def __init__(
        self,
        processors: Sequence[Processor],
        rejection_sink: Sink | None = None,
    ):
        """
        Initialize pipeline.

        Args:
            processors: Sequence of processors to chain
            rejection_sink: Optional sink for rejected items (Err values)
        """
        super().__init__()
        self.processors = list(processors)
        self.rejection_sink = rejection_sink

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
        Collect all output files from enabled processors and rejection sink.

        Returns:
            List of output file paths
        """
        artifacts: list[Path] = []
        for processor in self.processors:
            if processor.enabled:
                artifacts.extend(processor.artifacts())
        if self.rejection_sink:
            artifacts.extend(self.rejection_sink.artifacts())
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

    async def process(self, item: InT) -> Result[OutT, object]:
        """
        Process item through all enabled processors in sequence.

        Disabled processors are skipped. Each processor is responsible
        for updating its own statistics.

        Args:
            item: Input item

        Returns:
            Ok(result) on success, Err(reason) if rejected by any processor
        """
        current: Any = item
        for processor in self.processors:
            if not processor.enabled:
                continue

            result = await processor.process(current)  # type: ignore[arg-type]

            match result:
                case Ok(value=val):
                    current = val
                case Err(value=reason):
                    if self.rejection_sink:
                        await self.rejection_sink.push(errors.to_json(reason))
                    return result
                case other:
                    raise errors.MatchError(other)

        return Ok(cast(OutT, current))

    def __len__(self) -> int:
        """Return number of processors in pipeline."""
        return len(self.processors)

    def __repr__(self) -> str:
        """Return string representation."""
        processor_names = [type(p).__name__ for p in self.processors]
        return f"ProcessorPipeline([{', '.join(processor_names)}])"
