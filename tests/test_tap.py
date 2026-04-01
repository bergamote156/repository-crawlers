"""Tests for Tap processor."""

# pylint: disable=missing-function-docstring

import pytest

from crawlers.core.result import Ok
from crawlers.core.sink import Sink
from crawlers.processors import Tap


class CollectingSink(Sink[object]):
    """Sink that records all pushed items."""

    def __init__(self):
        self.items: list[object] = []

    async def open(self) -> None:
        pass

    async def push(self, item: object) -> None:
        self.items.append(item)

    async def close(self) -> None:
        pass


class TestTap:
    """Tests for the Tap processor."""

    @pytest.mark.asyncio
    async def test_passes_item_through_unchanged(self):
        sink = CollectingSink()
        tap = Tap(sink)
        result = await tap.process(42)
        assert result == Ok(42)

    @pytest.mark.asyncio
    async def test_pushes_item_to_sink(self):
        sink = CollectingSink()
        tap = Tap(sink)
        await tap.process("hello")
        assert sink.items == ["hello"]

    @pytest.mark.asyncio
    async def test_applies_transform_to_sink(self):
        sink = CollectingSink()
        tap = Tap(sink, transform=lambda x: x * 2)
        result = await tap.process(5)
        assert result == Ok(5)  # original value passed through
        assert sink.items == [10]  # transformed value sent to sink

    @pytest.mark.asyncio
    async def test_stats_pushed_incremented(self):
        tap = Tap(CollectingSink())
        await tap.process(1)
        await tap.process(2)
        assert tap.stats.pushed == 2
        assert tap.stats.processed == 2

    @pytest.mark.asyncio
    async def test_multiple_items_pushed_to_sink(self):
        sink = CollectingSink()
        tap = Tap(sink)
        for i in range(5):
            await tap.process(i)
        assert sink.items == [0, 1, 2, 3, 4]
