"""
Parallel crawl runner.

Consumes an async source iterator with a producer task, spawns
`concurrency` workers that call `process_fn(raw)`, validates successful
datasets, and routes
outcomes to framework sinks:

- `Ok(OnedataDataset)`  → validation, then processed or rejection sink
- `Err(failure)`        → rejection sink
- `None`                → silent skip
- unhandled exception   → counted as failure, logged
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import asyncio
from collections.abc import AsyncIterable, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, assert_never

from rich.progress import Progress, TaskID

from crawlers.core.jsonl import JSONLSink
from crawlers.core.result import Err, Ok, Result, failure_to_json
from crawlers.model.dataset import DatasetValidator, OnedataDataset
from crawlers.ui import console

_SENTINEL = object()

type ProcessFn[RawT] = Callable[[RawT], Awaitable[Result[OnedataDataset, Any] | None]]


@dataclass
class CrawlStats:
    """Coarse-grained stats for a crawl run."""

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


type StateCallback = Callable[[CrawlStats], Awaitable[None]]


@dataclass
class _CrawlRuntime[RawT]:
    """Private state shared by producer and workers during one crawl run."""

    source_iterator: AsyncIterable[RawT]
    process_fn: ProcessFn[RawT]
    validator: DatasetValidator
    processed_sink: JSONLSink
    rejection_sink: JSONLSink
    queue: asyncio.Queue[Any]
    stats: CrawlStats
    progress: Progress
    task_id: TaskID
    concurrency: int
    state_callback: StateCallback | None
    state_save_interval: int


async def run_parallel_crawl[RawT](  # noqa: PLR0913
    source_iterator: AsyncIterable[RawT],
    process_fn: ProcessFn[RawT],
    *,
    validator: DatasetValidator,
    processed_sink: JSONLSink,
    rejection_sink: JSONLSink,
    concurrency: int = 10,
    queue_size: int = 1000,
    max_items: int | None = None,
    state_callback: StateCallback | None = None,
    state_save_interval: int = 100,
) -> CrawlStats:
    """
    Fan out `process_fn` over items from `source_iterator`.

    A single producer pulls from the iterator and enqueues items;
    `concurrency` workers dequeue, invoke `process_fn`, validate successful
    datasets, and route the result to the appropriate sink.

    If the producer raises, the error propagates after all in-flight work
    drains — workers see the sentinel and stop, then the producer
    exception is re-raised so the caller can handle it.
    """
    queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=queue_size)
    stats = CrawlStats()

    with console.create_progress(total=max_items) as progress:
        task_id = progress.add_task("Processing", total=max_items)
        runtime = _CrawlRuntime(
            source_iterator=source_iterator,
            process_fn=process_fn,
            validator=validator,
            processed_sink=processed_sink,
            rejection_sink=rejection_sink,
            queue=queue,
            stats=stats,
            progress=progress,
            task_id=task_id,
            concurrency=concurrency,
            state_callback=state_callback,
            state_save_interval=state_save_interval,
        )

        producer_task = asyncio.create_task(_run_producer(runtime))
        workers = [asyncio.create_task(_run_worker(runtime, i)) for i in range(concurrency)]
        producer_error = await producer_task
        await asyncio.gather(*workers)
        await queue.join()

    if producer_error is not None:
        raise producer_error

    return stats


async def _run_producer[RawT](runtime: _CrawlRuntime[RawT]) -> BaseException | None:
    """Read source items into the queue and always stop workers afterwards."""
    try:
        async for item in runtime.source_iterator:
            await runtime.queue.put(item)
            runtime.stats.queued += 1
    except BaseException as exc:
        return exc
    finally:
        for _ in range(runtime.concurrency):
            await runtime.queue.put(_SENTINEL)

    return None


async def _run_worker[RawT](runtime: _CrawlRuntime[RawT], worker_id: int) -> None:
    """Drain queued items until a sentinel is received."""
    while True:
        item = await runtime.queue.get()
        if item is _SENTINEL:
            runtime.queue.task_done()
            break

        try:
            await _handle_job(runtime, item)
        except Exception as exc:
            item_str = str(item)[:50]
            runtime.progress.console.print(
                f"[warning]:warning:[/] Worker {worker_id} error processing {item_str}: {exc}"
            )
            runtime.stats.failed += 1
        finally:
            runtime.queue.task_done()
            runtime.progress.update(runtime.task_id, advance=1)
            await _save_state_if_needed(runtime)


async def _handle_job[RawT](runtime: _CrawlRuntime[RawT], item: RawT) -> None:
    """Run plugin processing for one item and route its result."""
    result = await runtime.process_fn(item)

    if isinstance(result, Ok):
        result = await runtime.validator.validate(result.value)

    match result:
        case None:
            runtime.stats.skipped += 1
        case Err(value=failure):
            await runtime.rejection_sink.push(failure_to_json(failure))
            runtime.stats.rejected += 1
        case Ok(value=dataset):
            await runtime.processed_sink.push(dataset.to_json())
            runtime.stats.processed += 1
        case other:
            assert_never(other)


async def _save_state_if_needed(runtime: _CrawlRuntime[Any]) -> None:
    """Persist stats on configured completion intervals."""
    if runtime.state_callback is None:
        return

    total_done = (
        runtime.stats.processed
        + runtime.stats.rejected
        + runtime.stats.skipped
        + runtime.stats.failed
    )
    if total_done > 0 and total_done % runtime.state_save_interval == 0:
        await runtime.state_callback(runtime.stats)
