"""Tests for OnedataConverter."""

# pylint: disable=redefined-outer-name,protected-access,missing-function-docstring

import pytest

from crawlers.core.result import Err
from crawlers.plugins.ecudo.metadata import EcudoOpenAIREBuilder
from crawlers.plugins.ecudo.parser import EcudoDataset, EcudoFile
from crawlers.processors.converters import OnedataConverter


@pytest.fixture
def converter():
    """Create converter instance."""
    return OnedataConverter(EcudoOpenAIREBuilder())


@pytest.fixture
def sample_record():
    """Create a sample EcudoRecord."""
    return EcudoDataset(
        identifier="urn:SDN:CDI:iopan.pl:uuid:test-123",
        title="Test Dataset / With Slash",
        description="Test description",
        publisher="Test Institute",
        issued="2024-01-15",
        language="English",
        keywords=["test"],
        files=[
            EcudoFile(path="data.csv", url="https://example.com/data.csv"),
            EcudoFile(path="readme.txt", url="https://example.com/readme.txt"),
        ],
    )


class TestOnedataConverter:
    """Tests for OnedataConverter."""

    @pytest.mark.asyncio
    async def test_converts_record(self, converter, sample_record):
        """Test basic conversion."""
        result = await converter.process(sample_record)
        dataset = result.value

        assert dataset.name == "Test Dataset / With Slash"
        assert dataset.location == "Test Dataset - With Slash"  # Slash replaced
        assert dataset.pid == "urn:SDN:CDI:iopan.pl:uuid:test-123"

    @pytest.mark.asyncio
    async def test_generates_metadata_xml(self, converter, sample_record):
        """Test that metadata XML is generated."""
        dataset = (await converter.process(sample_record)).value

        assert dataset.metadata_xml.startswith('<?xml version="1.0"')
        assert "Test Dataset" in dataset.metadata_xml

    @pytest.mark.asyncio
    async def test_converts_files(self, converter, sample_record):
        """Test file conversion."""
        dataset = (await converter.process(sample_record)).value

        assert len(dataset.files) == 2
        assert dataset.files[0].path == "data.csv"
        assert dataset.files[0].url == "https://example.com/data.csv"

    @pytest.mark.asyncio
    async def test_to_json(self, converter, sample_record):
        """Test to_json method."""
        d = (await converter.process(sample_record)).value.to_json()

        assert d["name"] == "Test Dataset / With Slash"
        assert d["location"] == "Test Dataset - With Slash"
        assert d["pid"] == "urn:SDN:CDI:iopan.pl:uuid:test-123"
        assert "metadata_xml" in d
        assert len(d["files"]) == 2
        assert d["files"][0]["path"] == "data.csv"
        assert "name" not in d["files"][0]

    @pytest.mark.asyncio
    async def test_rejects_duplicate_paths(self, converter):
        """Duplicate file paths should reject the dataset with Err."""
        record = EcudoDataset(
            identifier="urn:test:dup",
            title="Dup",
            description="",
            publisher="Test",
            issued="2024-01-01",
            language="en",
            keywords=[],
            files=[
                EcudoFile(path="data.csv", url="https://a.example/data.csv"),
                EcudoFile(path="data.csv", url="https://b.example/data.csv"),
            ],
        )

        result = await converter.process(record)

        assert isinstance(result, Err)
        assert result.value["reason"] == "duplicate_file_paths"
        assert result.value["detail"]["paths"] == ["data.csv"]
