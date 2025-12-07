"""Tests for OnedataConverter."""

import pytest

from ecudo.models import EcudoRecord, FileInfo
from ecudo.processors.converters import OnedataConverter
from ecudo.serializers import OpenAIRESerializer


@pytest.fixture
def serializer():
    """Create serializer instance."""
    return OpenAIRESerializer()


@pytest.fixture
def converter(serializer):
    """Create converter instance."""
    return OnedataConverter(serializer)


@pytest.fixture
def sample_record():
    """Create a sample EcudoRecord."""
    return EcudoRecord(
        identifier="urn:SDN:CDI:iopan.pl:uuid:test-123",
        title="Test Dataset / With Slash",
        description="Test description",
        publisher="Test Institute",
        issued="2024-01-15",
        language="en",
        keywords=["test"],
        files=[
            FileInfo(name="data.csv", url="https://example.com/data.csv"),
            FileInfo(name="readme.txt", url="https://example.com/readme.txt"),
        ],
    )


class TestOnedataConverter:
    """Tests for OnedataConverter."""

    @pytest.mark.asyncio
    async def test_converts_record(self, converter, sample_record):
        """Test basic conversion."""
        result = await converter.process(sample_record)

        assert result is not None
        assert result.name == "Test Dataset / With Slash"
        assert result.location == "Test Dataset - With Slash"  # Slash replaced
        assert result.pid == "urn:SDN:CDI:iopan.pl:uuid:test-123"

    @pytest.mark.asyncio
    async def test_generates_metadata_xml(self, converter, sample_record):
        """Test that metadata XML is generated."""
        result = await converter.process(sample_record)

        assert result is not None
        assert result.metadata_xml.startswith('<?xml version="1.0"')
        assert "Test Dataset" in result.metadata_xml

    @pytest.mark.asyncio
    async def test_converts_files(self, converter, sample_record):
        """Test file conversion."""
        result = await converter.process(sample_record)

        assert result is not None
        assert len(result.files) == 2
        assert result.files[0].name == "data.csv"
        assert result.files[0].url == "https://example.com/data.csv"
        assert result.files[0].path == "data.csv"

    @pytest.mark.asyncio
    async def test_to_dict(self, converter, sample_record):
        """Test to_dict method."""
        result = await converter.process(sample_record)

        assert result is not None
        d = result.to_dict()

        assert d["name"] == "Test Dataset / With Slash"
        assert d["location"] == "Test Dataset - With Slash"
        assert d["pid"] == "urn:SDN:CDI:iopan.pl:uuid:test-123"
        assert "metadata_xml" in d
        assert len(d["files"]) == 2
        assert d["files"][0]["name"] == "data.csv"

    @pytest.mark.asyncio
    async def test_stats(self, converter, sample_record):
        """Test statistics tracking."""
        await converter.process(sample_record)
        await converter.process(sample_record)

        stats = converter.get_stats()
        assert stats["converted"] == 2
