"""
Parallel Processing Orchestrator

Producer-consumer pattern for parallel fetching and processing.
Separates lightweight ID iteration from heavyweight metadata fetching.
"""

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator, Awaitable, Callable, Optional, TypeVar

T = TypeVar("T")
U = TypeVar("U")


@dataclass
class ProcessingStats:
    """Statistics from parallel processing run."""

    queued: int = 0
    fetched: int = 0
    processed: int = 0
    failed: int = 0

    def __str__(self) -> str:
        return (
            f"Queued: {self.queued}, Fetched: {self.fetched}, "
            f"Processed: {self.processed}, Failed: {self.failed}"
        )


class ParallelFetcher:
    """
    Generic parallel fetcher using producer-consumer pattern.

    Separates concerns:
    - ID source: Lightweight async iterator producing IDs (sequential)
    - Fetcher: Heavyweight function fetching data by ID (parallelized)
    - Processor: Function processing fetched data (sequential per item)

    This design allows efficient parallel HTTP requests while maintaining
    backpressure through a bounded queue.

    Usage:
        fetcher = ParallelFetcher(concurrency=128)
        stats = await fetcher.run(
            id_source=record_id_iterator,
            fetcher=client.get_record_metadata,
            processor=pipeline.process,
        )
    """

    def __init__(
        self,
        concurrency: int = 128,
        queue_size: int = 1000,
    ):
        """
        Initialize parallel fetcher.

        Args:
            concurrency: Number of concurrent workers
            queue_size: Maximum queue size (backpressure)
        """
        self.concurrency = concurrency
        self.queue_size = queue_size

    async def run(
        self,
        id_source: AsyncIterator[str],
        fetcher: Callable[[str], Awaitable[Optional[T]]],
        processor: Callable[[T], Awaitable[Optional[U]]],
    ) -> ProcessingStats:
        """
        Run parallel fetch and process pipeline.

        Args:
            id_source: Async iterator yielding IDs (lightweight)
            fetcher: Async function to fetch data by ID (heavyweight, parallelized)
            processor: Async function to process fetched data

        Returns:
            Processing statistics
        """
        queue: asyncio.Queue[Optional[str]] = asyncio.Queue(maxsize=self.queue_size)
        stats = ProcessingStats()

        async def producer():
            """Push IDs from source to queue."""
            try:
                async for record_id in id_source:
                    await queue.put(record_id)
                    stats.queued += 1
            except Exception as e:
                print(f"❌ Producer error: {e}")
            finally:
                # Send sentinel values to signal workers to stop
                for _ in range(self.concurrency):
                    await queue.put(None)

        async def worker(worker_id: int):
            """Fetch and process records from queue."""
            while True:
                record_id = await queue.get()

                if record_id is None:  # Sentinel - stop
                    queue.task_done()
                    break

                try:
                    # Fetch data (parallelized across workers)
                    data = await fetcher(record_id)

                    if data:
                        stats.fetched += 1

                        # Process data
                        result = await processor(data)
                        if result:
                            stats.processed += 1
                    else:
                        stats.failed += 1

                except Exception as e:
                    print(
                        f"⚠️ Worker {worker_id} error processing {record_id[:50]}: {e}"
                    )
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
        print(f"\n✅ Parallel processing complete!")
        print(f"   {stats}")

        return stats
