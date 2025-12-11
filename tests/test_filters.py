"""Tests for DiversityFilter."""

import pytest

from ecudo.models import EcudoDataset, EcudoFile
from ecudo.processors import DiversityFilter


def make_record(identifier: str, title: str) -> EcudoDataset:
    """Helper to create a test record."""
    return EcudoDataset(
        identifier=identifier,
        title=title,
        description="",
        publisher="Test",
        issued="2024-01-01",
        language="en",
        keywords=[],
        files=[EcudoFile(name="data.zip", url="https://example.com/data.zip")],
    )


class TestDiversityFilter:
    """Tests for DiversityFilter processor."""

    @pytest.mark.asyncio
    async def test_accepts_first_record(self):
        """Test that first record is always accepted."""
        filter = DiversityFilter(max_similar=3, similarity_threshold=0.85)

        record = make_record("id1", "Unique Dataset Title")
        result = await filter.process(record)

        assert result is not None
        assert result.identifier == "id1"
        assert filter._accepted == 1
        assert filter._skipped == 0

    @pytest.mark.asyncio
    async def test_accepts_different_titles(self):
        """Test that records with different titles are accepted."""
        filter = DiversityFilter(max_similar=3, similarity_threshold=0.85)

        r1 = make_record("id1", "Ocean Temperature Data")
        r2 = make_record("id2", "Satellite Imagery Collection")
        r3 = make_record("id3", "Weather Station Readings")

        assert await filter.process(r1) is not None
        assert await filter.process(r2) is not None
        assert await filter.process(r3) is not None

        assert filter._accepted == 3
        assert filter._skipped == 0
        assert len(filter._title_groups) == 3

    @pytest.mark.asyncio
    async def test_limits_similar_titles(self):
        """Test that similar titles are limited."""
        filter = DiversityFilter(max_similar=2, similarity_threshold=0.85)

        # These titles are very similar (>85%)
        r1 = make_record("id1", "VDR Data from Research Vessel")
        r2 = make_record("id2", "VDR Data from Research Vessel")
        r3 = make_record("id3", "VDR Data from Research Vessel")

        result1 = await filter.process(r1)
        result2 = await filter.process(r2)
        result3 = await filter.process(r3)

        assert result1 is not None  # First accepted
        assert result2 is not None  # Second accepted (limit=2)
        assert result3 is None  # Third rejected

        assert filter._accepted == 2
        assert filter._skipped == 1

    @pytest.mark.asyncio
    async def test_similarity_threshold(self):
        """Test that similarity threshold works correctly."""
        # High threshold - more strict
        filter_strict = DiversityFilter(max_similar=1, similarity_threshold=0.95)

        r1 = make_record("id1", "Ocean Data 2024")
        r2 = make_record("id2", "Ocean Data 2023")

        assert await filter_strict.process(r1) is not None
        assert await filter_strict.process(r2) is not None  # Different enough

        # Low threshold - more lenient
        filter_lenient = DiversityFilter(max_similar=1, similarity_threshold=0.5)

        r3 = make_record("id3", "Ocean Data 2024")
        r4 = make_record("id4", "Ocean Data 2023")

        assert await filter_lenient.process(r3) is not None
        assert await filter_lenient.process(r4) is None  # Too similar

    @pytest.mark.asyncio
    async def test_empty_title_accepted(self):
        """Test that records without title are always accepted."""
        filter = DiversityFilter(max_similar=1, similarity_threshold=0.85)

        r1 = make_record("id1", "")
        r2 = make_record("id2", "")

        assert await filter.process(r1) is not None
        assert await filter.process(r2) is not None

    @pytest.mark.asyncio
    async def test_multiple_groups(self):
        """Test handling of multiple distinct groups."""
        filter = DiversityFilter(max_similar=2, similarity_threshold=0.85)

        # Group 1: VDR Data
        vdr1 = make_record("vdr1", "VDR Data Recording 1")
        vdr2 = make_record("vdr2", "VDR Data Recording 2")
        vdr3 = make_record("vdr3", "VDR Data Recording 3")

        # Group 2: CTD Data
        ctd1 = make_record("ctd1", "CTD Measurements Station A")
        ctd2 = make_record("ctd2", "CTD Measurements Station B")
        ctd3 = make_record("ctd3", "CTD Measurements Station C")

        # Process interleaved
        assert await filter.process(vdr1) is not None
        assert await filter.process(ctd1) is not None
        assert await filter.process(vdr2) is not None
        assert await filter.process(ctd2) is not None
        assert await filter.process(vdr3) is None  # VDR group full
        assert await filter.process(ctd3) is None  # CTD group full

        assert filter._accepted == 4
        assert filter._skipped == 2
        assert len(filter._title_groups) == 2

    @pytest.mark.asyncio
    async def test_close_prints_statistics(self, capsys):
        """Test that close() prints statistics."""
        filter = DiversityFilter(max_similar=2, similarity_threshold=0.85)

        # Use very different titles to ensure separate groups
        await filter.process(make_record("id1", "Ocean Temperature Measurements"))
        await filter.process(make_record("id2", "Satellite Imagery Collection"))

        await filter.close()

        captured = capsys.readouterr()
        assert "Diversity Filter Statistics" in captured.out
        assert "Total groups: 2" in captured.out
        assert "Accepted: 2" in captured.out
