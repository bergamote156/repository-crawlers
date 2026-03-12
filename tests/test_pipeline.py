"""Tests for ProcessorPipeline."""

# pylint: disable=redefined-outer-name,protected-access,missing-function-docstring

import pytest

from crawlers.core.abc.processor import Processor, ProcessorStats
from crawlers.core.processors.pipeline import ProcessorPipeline


class PassThroughProcessor(Processor[int, int, ProcessorStats]):
    """Simple processor that passes items through unchanged."""

    def __init__(self):
        super().__init__()
        self.opened = False
        self.closed = False
        self.processed_items = []

    async def open(self) -> None:
        self.opened = True

    async def close(self) -> None:
        self.closed = True

    async def process(self, item: int) -> int:
        self.processed_items.append(item)
        return item


class DoubleProcessor(Processor[int, int, ProcessorStats]):
    """Processor that doubles the input value."""

    async def process(self, item: int) -> int:
        self.stats.processed += 1
        return item * 2


class AddProcessor(Processor[int, int, ProcessorStats]):
    """Processor that adds a fixed value."""

    def __init__(self, value: int):
        super().__init__()
        self.value = value

    async def process(self, item: int) -> int:
        self.stats.processed += 1
        return item + self.value


class FilterEvenProcessor(Processor[int, int, ProcessorStats]):
    """Processor that filters out even numbers."""

    async def process(self, item: int) -> int | None:
        if item % 2 == 0:
            self.stats.filtered += 1
            return None  # Filter out even numbers
        self.stats.processed += 1
        return item


class IntToStrProcessor(Processor[int, str, ProcessorStats]):
    """Processor that converts int to string."""

    async def process(self, item: int) -> str:
        self.stats.processed += 1
        return f"value:{item}"


class TestProcessorPipeline:
    """Tests for ProcessorPipeline class."""

    @pytest.mark.asyncio
    async def test_empty_pipeline(self):
        """Test pipeline with no processors."""
        pipeline = ProcessorPipeline([])

        await pipeline.open()
        result = await pipeline.process(42)
        await pipeline.close()

        assert result == 42

    @pytest.mark.asyncio
    async def test_single_processor(self):
        """Test pipeline with one processor."""
        processor = DoubleProcessor()
        pipeline = ProcessorPipeline([processor])

        await pipeline.open()
        result = await pipeline.process(5)
        await pipeline.close()

        assert result == 10

    @pytest.mark.asyncio
    async def test_multiple_processors(self):
        """Test pipeline with multiple processors in sequence."""
        pipeline = ProcessorPipeline(
            [
                DoubleProcessor(),  # 5 -> 10
                AddProcessor(3),  # 10 -> 13
                DoubleProcessor(),  # 13 -> 26
            ]
        )

        await pipeline.open()
        result = await pipeline.process(5)
        await pipeline.close()

        assert result == 26

    @pytest.mark.asyncio
    async def test_filter_stops_pipeline(self):
        """Test that returning None stops the pipeline."""
        double = DoubleProcessor()
        filter_even = FilterEvenProcessor()
        add = AddProcessor(100)

        pipeline = ProcessorPipeline([double, filter_even, add])

        await pipeline.open()

        # 5 * 2 = 10, filtered out (even)
        result = await pipeline.process(5)
        assert result is None
        assert filter_even.stats.filtered == 1

        # 3 * 2 = 6, filtered out (even)
        result = await pipeline.process(3)
        assert result is None
        assert filter_even.stats.filtered == 2

        # 2 * 2 = 4, filtered out (even)
        result = await pipeline.process(2)
        assert result is None

        await pipeline.close()

    @pytest.mark.asyncio
    async def test_filter_passes_odd(self):
        """Test that odd numbers pass through filter."""
        # Pipeline: double first (produces odd result for input 0.5 not possible)
        # So let's use: add 1, then filter
        add = AddProcessor(1)
        filter_even = FilterEvenProcessor()
        double = DoubleProcessor()
        pipeline = ProcessorPipeline([add, filter_even, double])

        await pipeline.open()
        result = await pipeline.process(4)
        await pipeline.close()

        assert result == 10
        assert add.stats.processed == 1
        assert filter_even.stats.filtered == 0

    @pytest.mark.asyncio
    async def test_lifecycle_methods_called(self):
        """Test that open() and close() are called on all processors."""
        p1 = PassThroughProcessor()
        p2 = PassThroughProcessor()
        p3 = PassThroughProcessor()

        pipeline = ProcessorPipeline([p1, p2, p3])

        # Before open
        assert not p1.opened and not p2.opened and not p3.opened

        await pipeline.open()

        # After open
        assert p1.opened and p2.opened and p3.opened
        assert not p1.closed and not p2.closed and not p3.closed

        await pipeline.close()

        # After close
        assert p1.closed and p2.closed and p3.closed

    @pytest.mark.asyncio
    async def test_items_flow_through_all_processors(self):
        """Test that items pass through every processor in order."""
        p1 = PassThroughProcessor()
        p2 = PassThroughProcessor()
        p3 = PassThroughProcessor()

        pipeline = ProcessorPipeline([p1, p2, p3])

        await pipeline.open()
        await pipeline.process(1)
        await pipeline.process(2)
        await pipeline.process(3)
        await pipeline.close()

        assert p1.processed_items == [1, 2, 3]
        assert p2.processed_items == [1, 2, 3]
        assert p3.processed_items == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_type_transformation(self):
        """Test pipeline with type-changing processors."""
        pipeline = ProcessorPipeline(
            [
                DoubleProcessor(),  # int -> int
                IntToStrProcessor(),  # int -> str
            ]
        )

        await pipeline.open()
        result = await pipeline.process(21)
        await pipeline.close()

        assert result == "value:42"

    def test_len(self):
        """Test __len__ method."""
        pipeline = ProcessorPipeline(
            [
                DoubleProcessor(),
                AddProcessor(1),
                PassThroughProcessor(),
            ]
        )
        assert len(pipeline) == 3

    def test_repr(self):
        """Test __repr__ method."""
        pipeline = ProcessorPipeline(
            [
                DoubleProcessor(),
                FilterEvenProcessor(),
            ]
        )
        repr_str = repr(pipeline)

        assert "ProcessorPipeline" in repr_str
        assert "DoubleProcessor" in repr_str
        assert "FilterEvenProcessor" in repr_str

    @pytest.mark.asyncio
    async def test_statistics_tracking(self):
        """Test that processed and filtered counts are tracked."""
        pipeline = ProcessorPipeline(
            [
                DoubleProcessor(),
                FilterEvenProcessor(),  # All doubled values are even, so all filtered
            ]
        )

        await pipeline.open()

        for i in range(5):
            await pipeline.process(i)

        await pipeline.close()

        assert pipeline.processors[1].stats.filtered == 5
        assert pipeline.processors[1].stats.processed == 0
