"""
Parallel crawl runner for `SimpleCrawlerPlugin`.

Consumes an async source iterator with a producer task, spawns
`concurrency` workers that call `parse_fn(raw)`, and routes the
outcome to the framework sinks:

- `Ok(OnedataDataset)`  → processed sink
- `Err(failure)`        → rejection sink
- `None`                → silent skip
- exception             → counted as failure, logged
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import asyncio
from collections.abc import AsyncIterable, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from crawlers.core.errors import to_json as error_to_json
from crawlers.core.onedata import OnedataDataset
from crawlers.core.result import Err, Ok, Result
from crawlers.sinks import JSONLSink
from crawlers.ui import console


@dataclass
class CrawlStats:
    """Coarse-grained stats for a simple crawl."""

    queued: int = 0
    processed: int = 0
    rejected: int = 0
    skipped: int = 0
    failed: int = 0

    def __str__(self) -> str:
        return (
            f"Queued: {self.queued}, Processed: {self.processed}, "
            f"Rejected: {self.rejected}, Skipped: {self.skipped}, "
            f"Failed: {self.failed}"
        )


# pylint: disable=too-many-locals,too-many-arguments
async def run_parallel_crawl[RawT](
    source_iterator: AsyncIterable[RawT],
    parse_fn: Callable[[RawT], Awaitable[Result[OnedataDataset, Any] | None]],
    *,
    processed_sink: JSONLSink,
    rejection_sink: JSONLSink,
    concurrency: int = 10,
    queue_size: int = 1000,
    max_items: int | None = None,
    state_callback: Callable[[CrawlStats], Awaitable[None]] | None = None,
    state_save_interval: int = 100,
) -> CrawlStats:
    """
    Fan out `parse_fn` over items from `source_iterator`.

    A single producer pulls from the iterator and enqueues items; `concurrency`
    workers dequeue, invoke `parse_fn`, and route the result to the appropriate
    sink. Shows live progress tracking. `state_callback` is invoked every
    `state_save_interval` processed items so the caller can persist intermediate
    stats for resume support.
    """
    queue: asyncio.Queue[RawT | None] = asyncio.Queue(maxsize=queue_size)
    stats = CrawlStats()
    progress = console.create_progress(total=max_items)

    async def producer() -> None:
        try:
            async for item in source_iterator:
                await queue.put(item)
                stats.queued += 1
        except Exception as exc:  # pylint: disable=broad-exception-caught
            progress.console.print(f"[error]:cross_mark:[/] Producer error: {exc}")
        finally:
            for _ in range(concurrency):
                await queue.put(None)

    async def worker(worker_id: int, task_id) -> None:
        while True:
            item = await queue.get()
            if item is None:
                queue.task_done()
                break

            try:
                result = await parse_fn(item)

                if result is None:
                    stats.skipped += 1
                elif isinstance(result, Ok):
                    await processed_sink.push(result.value.to_json())
                    stats.processed += 1
                elif isinstance(result, Err):
                    await rejection_sink.push(error_to_json(result.value))
                    stats.rejected += 1
            except Exception as exc:  # pylint: disable=broad-exception-caught
                item_str = str(item)[:50]
                progress.console.print(
                    f"[warning]:warning:[/] Worker {worker_id} error "
                    f"processing {item_str}: {exc}"
                )
                stats.failed += 1
            finally:
                queue.task_done()
                progress.update(task_id, advance=1)

                if state_callback:
                    total_done = (
                        stats.processed + stats.rejected + stats.skipped + stats.failed
                    )
                    if total_done > 0 and total_done % state_save_interval == 0:
                        await state_callback(stats)

    with progress:
        task_id = progress.add_task("Processing", total=max_items)
        producer_task = asyncio.create_task(producer())
        workers = [asyncio.create_task(worker(i, task_id)) for i in range(concurrency)]
        await producer_task
        await asyncio.gather(*workers)
        await queue.join()

    return stats
