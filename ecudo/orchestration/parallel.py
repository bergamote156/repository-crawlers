"""
Parallel Processing Orchestrator

Producer-consumer pattern for parallel fetching and processing.
Separates lightweight ID iteration from heavyweight metadata fetching.
"""

import asyncio
from collections.abc import AsyncIterable
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


async def run_parallel_pipeline[I, O](
    id_source: AsyncIterable[I],
    pipeline: Processor[I, O],
    *,
    concurrency: int = 128,
    queue_size: int = 1000,
    verbose: bool = True,
) -> ProcessingStats:
    """
    Run pipeline in parallel using producer-consumer pattern.

    Separates concerns:
    - ID source: Lightweight async iterator producing IDs (sequential)
    - Pipeline: Processor chain that handles fetch + transform + write

    This design allows efficient parallel HTTP requests while maintaining
    backpressure through a bounded queue.

    Args:
        id_source: Async iterator yielding input items (e.g., record IDs)
        pipeline: Processor pipeline to apply to each item
        concurrency: Number of concurrent workers (default: 128)
        queue_size: Maximum queue size for backpressure (default: 1000)
        verbose: Print progress messages (default: True)

    Returns:
        Processing statistics

    Example:
        pipeline = ProcessorPipeline([
            MetadataFetcher(client, parser),
            URLValidator(client),
            DiversityFilter(...),
            RawRecordWriter(raw_output),
            OnedataConverter(openaire.generate_xml),
            JSONLWriter(processed_output),
        ])

        stats = await run_parallel_pipeline(
            id_source=record_id_iterator,
            pipeline=pipeline,
            concurrency=128,
            queue_size=1000,
        )
    """
    queue: asyncio.Queue[I | None] = asyncio.Queue(maxsize=queue_size)
    stats = ProcessingStats()

    def _log(message: str) -> None:
        """Print message if verbose mode is enabled."""
        if verbose:
            print(message)

    async def producer():
        """Push items from source to queue."""
        try:
            async for item in id_source:
                await queue.put(item)
                stats.queued += 1
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _log(f"❌ Producer error: {exc}")
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
                result = await pipeline.process(item)
                if result is not None:
                    stats.processed += 1
                # If result is None, item was filtered (not a failure)

            except Exception as exc:  # pylint: disable=broad-exception-caught
                item_str = str(item)[:50] if item else "?"
                _log(f"⚠️ Worker {worker_id} error processing {item_str}: {exc}")
                stats.failed += 1
            finally:
                queue.task_done()

    # Start producer and workers
    producer_task = asyncio.create_task(producer())
    worker_tasks = [asyncio.create_task(worker(i)) for i in range(concurrency)]

    # Wait for producer to finish
    await producer_task

    # Wait for all workers to finish
    await asyncio.gather(*worker_tasks)

    # Print summary
    _log("\n✅ Parallel processing complete!")
    _log(f"   {stats}")

    return stats
