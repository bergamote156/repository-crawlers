"""
Parallel Processing Orchestrator

Producer-consumer pattern for parallel fetching and processing.
Separates lightweight ID iteration from heavyweight metadata fetching.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import asyncio
from collections.abc import AsyncIterable
from dataclasses import dataclass

from ecudo import output
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


async def run_parallel_pipeline[I, O](
    dataset_id_source: AsyncIterable[I],
    dataset_pipeline: Processor[I, O],
    *,
    concurrency: int = 128,
    queue_size: int = 1000,
) -> None:
    """
    Run pipeline in parallel using producer-consumer pattern.

    Separates concerns:
    - ID source: Lightweight async iterator producing IDs (sequential)
    - Pipeline: Processor chain that handles fetch + transform + write

    This design allows efficient parallel HTTP requests while maintaining
    backpressure through a bounded queue.

    Args:
        dataset_id_source: Async iterator yielding input items (e.g., dataset IDs)
        dataset_pipeline: Processor pipeline to apply to each item
        concurrency: Number of concurrent workers (default: 128)
        queue_size: Maximum queue size for backpressure (default: 1000)

    Returns:
        Processing statistics

    Example:
        pipeline = ProcessorPipeline([
            DatasetFetcher(...),
            DiversityFilter(...),
            OnedataConverter(...),
            JSONLWriter(...),
        ])

        stats = await run_parallel_pipeline(
            dataset_id_source=id_iterator,
            dataset_pipeline=pipeline,
            concurrency=128,
            queue_size=1000,
        )
    """
    queue: asyncio.Queue[I | None] = asyncio.Queue(maxsize=queue_size)
    stats = ProcessingStats()

    async def producer():
        """Push items from source to queue."""
        try:
            async for item in dataset_id_source:
                await queue.put(item)
                stats.queued += 1
        except Exception as exc:  # pylint: disable=broad-exception-caught
            output.error(f"Producer error: {exc}")
        finally:
            # Send sentinel values to signal workers to stop
            for _ in range(concurrency):
                await queue.put(None)

    async def worker(worker_id: int):
        """Process items from queue through pipeline."""
        while True:
            item = await queue.get()

            if item is None:  # Sentinel - stop
                queue.task_done()
                break

            try:
                result = await dataset_pipeline.process(item)
                if result is not None:
                    stats.processed += 1
                # If result is None, item was filtered (not a failure)

            except Exception as exc:  # pylint: disable=broad-exception-caught
                item_str = str(item)[:50] if item else "?"
                output.warning(f"Worker {worker_id} error processing {item_str}: {exc}")
                stats.failed += 1
            finally:
                queue.task_done()

    producer_task = asyncio.create_task(producer())
    worker_tasks = [asyncio.create_task(worker(i)) for i in range(concurrency)]

    # Wait for producer to finish
    await producer_task

    # Wait for all workers to finish
    await asyncio.gather(*worker_tasks)

    # Print summary
    output.info("\n✅ Parallel processing complete!")
    output.info(f"   {stats}")
