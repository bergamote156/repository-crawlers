"""
Parallel Processing Orchestrator

Producer-consumer pattern for parallel fetching and processing.
Separates lightweight ID iteration from heavyweight metadata fetching.
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

from ecudo.processors.base import Processor


@dataclass
class ProcessingStats:
    """Statistics from parallel processing run."""

    queued: int = 0
    processed: int = 0
    failed: int = 0

    def __str__(self) -> str:
        return (
            f"Queued: {self.queued}, Processed: {self.processed}, "
            f"Failed: {self.failed}"
        )


class ParallelFetcher[I, O]:
    """
    Generic parallel processor using producer-consumer pattern.

    Separates concerns:
    - ID source: Lightweight async iterator producing IDs (sequential)
    - Pipeline: Processor chain that handles fetch + transform + write

    This design allows efficient parallel HTTP requests while maintaining
    backpressure through a bounded queue.

    Usage:
        pipeline = ProcessorPipeline([
            MetadataFetcher(client, parser),
            URLValidator(client),
            DiversityFilter(...),
            RawRecordWriter(raw_output),
            OnedataConverter(serializer),
            JSONLWriter(processed_output),
        ])

        fetcher = ParallelFetcher(concurrency=128)
        stats = await fetcher.run(
            id_source=record_id_iterator,
            pipeline=pipeline,
        )
    """

    def __init__(
        self,
        concurrency: int = 128,
        queue_size: int = 1000,
        verbose: bool = True,
    ):
        """
        Initialize parallel fetcher.

        Args:
            concurrency: Number of concurrent workers
            queue_size: Maximum queue size (backpressure)
            verbose: Print progress messages
        """
        self.concurrency = concurrency
        self.queue_size = queue_size
        self.verbose = verbose

    def _log(self, message: str) -> None:
        """Print message if verbose mode is enabled."""
        if self.verbose:
            print(message)

    async def run(
        self,
        id_source: AsyncIterator[I],
        pipeline: Processor[I, O],
    ) -> ProcessingStats:
        """
        Run parallel processing pipeline.

        Args:
            id_source: Async iterator yielding input items (e.g., record IDs)
            pipeline: Processor pipeline to apply to each item

        Returns:
            Processing statistics
        """
        queue: asyncio.Queue[I | None] = asyncio.Queue(maxsize=self.queue_size)
        stats = ProcessingStats()

        async def producer():
            """Push items from source to queue."""
            try:
                async for item in id_source:
                    await queue.put(item)
                    stats.queued += 1
            except Exception as e:
                self._log(f"❌ Producer error: {e}")
            finally:
                # Send sentinel values to signal workers to stop
                for _ in range(self.concurrency):
                    await queue.put(None)

        async def worker(worker_id: int):
            """Process items from queue through pipeline."""
            while True:
                item = await queue.get()

                if item is None:  # Sentinel - stop
                    queue.task_done()
                    break

                try:
                    result = await pipeline.process(item)
                    if result is not None:
                        stats.processed += 1
                    # If result is None, item was filtered (not a failure)

                except Exception as e:
                    item_str = str(item)[:50] if item else "?"
                    self._log(f"⚠️ Worker {worker_id} error processing {item_str}: {e}")
                    stats.failed += 1
                finally:
                    queue.task_done()

        # Start producer and workers
        producer_task = asyncio.create_task(producer())
        worker_tasks = [asyncio.create_task(worker(i)) for i in range(self.concurrency)]

        # Wait for producer to finish
        await producer_task

        # Wait for all workers to finish
        await asyncio.gather(*worker_tasks)

        # Print summary
        self._log(f"\n✅ Parallel processing complete!")
        self._log(f"   {stats}")

        return stats
