"""Tests for Tap processor."""

# pylint: disable=missing-function-docstring

import pytest

from crawlers.core.processors.tap import Tap
from crawlers.core.result import Ok
from crawlers.core.sinks import NullSink, Sink


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
    async def test_transform_does_not_affect_pipeline_value(self):
        """The transform only affects what goes to the sink, not the returned value."""
        sink = CollectingSink()
        tap = Tap(sink, transform=lambda x: {"wrapped": x})
        result = await tap.process("raw")
        assert result.unwrap() == "raw"
        assert sink.items == [{"wrapped": "raw"}]

    @pytest.mark.asyncio
    async def test_stats_pushed_incremented(self):
        tap = Tap(NullSink())
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

    def test_describe_includes_sink_repr(self):
        sink = NullSink()
        tap = Tap(sink)
        assert "NullSink" in tap.describe()

    def test_artifacts_delegated_to_sink(self):
        tap = Tap(NullSink())
        assert tap.artifacts() == []
