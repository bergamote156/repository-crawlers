"""
Parallel Execution

Utilities for running pipelines concurrently with progress tracking.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import asyncio
from dataclasses import dataclass
from typing import AsyncIterable, Awaitable, Callable

from crawlers.core.processors.pipeline import ProcessorPipeline
from crawlers.core.ui import console


@dataclass
class CrawlStats:
    """Aggregated statistics from parallel crawl execution."""

    queued: int = 0
    processed: int = 0
    filtered: int = 0
    failed: int = 0

    def __str__(self) -> str:
        return (
            f"Queued: {self.queued}, Processed: {self.processed}, "
            f"Filtered: {self.filtered}, Failed: {self.failed}"
        )


# pylint: disable=too-many-locals,too-many-arguments
async def run_parallel_pipeline[InT, OutT](
    source_iterator: AsyncIterable[InT],
    pipeline: ProcessorPipeline[InT, OutT],
    *,
    concurrency: int = 10,
    queue_size: int = 1000,
    max_items: int | None = None,
    state_callback: Callable[[CrawlStats], Awaitable[None]] | None = None,
    state_save_interval: int = 100,
) -> CrawlStats:
    """
    Run pipeline concurrently on items from source iterator.

    Uses a queue to buffer items from the iterator and a pool of workers
    to process them through the pipeline. Shows live progress tracking.

    Args:
        source_iterator: Async iterator yielding input items
        pipeline: The processor pipeline to run
        concurrency: Number of concurrent workers
        queue_size: Max size of the buffer queue
        max_items: Maximum items to process (enables progress bar if set)
        state_callback: Optional callback invoked periodically with current stats.
                        Used by BaseCrawler to persist state for resume support.
        state_save_interval: Invoke state_callback every N processed items

    Returns:
        CrawlStats with aggregated statistics
    """
    queue: asyncio.Queue[InT | None] = asyncio.Queue(maxsize=queue_size)
    stats = CrawlStats()

    # Create progress with appropriate display based on whether total is known
    progress = console.create_progress(total=max_items)

    # Producer task: reads from iterator and puts into queue
    async def producer():
        try:
            async for item in source_iterator:
                await queue.put(item)
                stats.queued += 1
        except Exception as e:  # pylint: disable=broad-exception-caught
            progress.console.print(f"[error]:cross_mark:[/] Producer error: {e}")
        finally:
            # Signal workers to stop
            for _ in range(concurrency):
                await queue.put(None)

    # Worker task: reads from queue and runs pipeline
    async def worker(worker_id: int, task_id):
        while True:
            item = await queue.get()

            if item is None:  # Sentinel - stop
                queue.task_done()
                break

            try:
                result = await pipeline.process(item)
                if result.is_ok():
                    stats.processed += 1
                else:
                    stats.filtered += 1
            except Exception as e:  # pylint: disable=broad-exception-caught
                item_str = str(item)[:50] if item else "?"
                progress.console.print(
                    f"[warning]:warning:[/] Worker {worker_id} error processing {item_str}: {e}"
                )
                stats.failed += 1
            finally:
                queue.task_done()
                progress.update(task_id, advance=1)

                # Periodically save state for resume support
                if state_callback:
                    total_done = stats.processed + stats.filtered + stats.failed
                    if total_done > 0 and total_done % state_save_interval == 0:
                        await state_callback(stats)

    # Run with live progress display
    with progress:
        progress_task_id = progress.add_task("Processing", total=max_items)

        # Start producer
        producer_task = asyncio.create_task(producer())

        # Start workers
        workers = [
            asyncio.create_task(worker(i, progress_task_id)) for i in range(concurrency)
        ]

        # Wait for producer to finish (iterating over all items)
        await producer_task

        # Wait for workers to finish processing the queue (including None signals)
        await asyncio.gather(*workers)
        await queue.join()

    return stats
