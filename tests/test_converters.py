"""Tests for OnedataConverter and path collision resolution."""

# pylint: disable=redefined-outer-name,protected-access,missing-function-docstring

import pytest

from ecudo.metadata import openaire
from ecudo.models import EcudoDataset, EcudoFile
from ecudo.processors.converters import OnedataConverter, resolve_path_collisions


@pytest.fixture
def converter():
    """Create converter instance."""
    return OnedataConverter(openaire.generate_xml)


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
            EcudoFile(name="data.csv", url="https://example.com/data.csv"),
            EcudoFile(name="readme.txt", url="https://example.com/readme.txt"),
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
    async def test_to_json(self, converter, sample_record):
        """Test to_json method."""
        result = await converter.process(sample_record)

        assert result is not None
        d = result.to_json()

        assert d["name"] == "Test Dataset / With Slash"
        assert d["location"] == "Test Dataset - With Slash"
        assert d["pid"] == "urn:SDN:CDI:iopan.pl:uuid:test-123"
        assert "metadata_xml" in d
        assert len(d["files"]) == 2
        assert d["files"][0]["name"] == "data.csv"

    @pytest.mark.asyncio
    async def test_resolves_path_collisions(self, converter):
        """Test that duplicate filenames get unique paths."""
        record = EcudoDataset(
            identifier="urn:test:collision",
            title="Collision Test",
            description="Testing path collision resolution",
            publisher="Test",
            issued="2024-01-01",
            language="en",
            keywords=[],
            files=[
                EcudoFile(
                    name="23",
                    url="https://example.com/api/stats/hl/station/26015/2013/2/23",
                ),
                EcudoFile(
                    name="23",
                    url="https://example.com/api/data/tabular/hl/station/26015/2013/2/23",
                ),
            ],
        )

        result = await converter.process(record)

        assert result is not None
        assert len(result.files) == 2
        # Paths should be resolved with enough segments to be unique
        assert result.files[0].path == "stats/hl/station/26015/2013/2/23"
        assert result.files[1].path == "tabular/hl/station/26015/2013/2/23"


class TestResolvePathCollisions:
    """Tests for resolve_path_collisions function."""

    def test_empty_list(self):
        """Empty file list returns empty path list."""
        assert resolve_path_collisions([]) == []

    def test_single_file(self):
        """Single file gets simple path."""
        files = [EcudoFile(name="data.csv", url="https://example.com/data.csv")]

        paths = resolve_path_collisions(files)

        assert paths == ["data.csv"]

    def test_no_collisions(self):
        """Files with unique names keep simple paths."""
        files = [
            EcudoFile(name="data.csv", url="https://example.com/a/data.csv"),
            EcudoFile(name="readme.txt", url="https://example.com/b/readme.txt"),
        ]

        paths = resolve_path_collisions(files)

        assert paths == ["data.csv", "readme.txt"]

    def test_simple_collision(self):
        """Two files with same name get disambiguated."""
        files = [
            EcudoFile(name="data.csv", url="https://example.com/raw/data.csv"),
            EcudoFile(name="data.csv", url="https://example.com/processed/data.csv"),
        ]

        paths = resolve_path_collisions(files)

        assert paths == ["raw/data.csv", "processed/data.csv"]

    def test_deep_collision(self):
        """Collisions requiring multiple path segments to resolve."""
        files = [
            EcudoFile(name="23", url="https://example.com/api/stats/hl/2013/2/23"),
            EcudoFile(name="23", url="https://example.com/api/data/hl/2013/2/23"),
        ]

        paths = resolve_path_collisions(files)

        assert paths == ["stats/hl/2013/2/23", "data/hl/2013/2/23"]

    def test_multiple_collisions(self):
        """Multiple files with same name all get unique paths."""
        files = [
            EcudoFile(name="data.bin", url="https://example.com/a/data.bin"),
            EcudoFile(name="data.bin", url="https://example.com/b/data.bin"),
            EcudoFile(name="data.bin", url="https://example.com/c/data.bin"),
        ]

        paths = resolve_path_collisions(files)

        assert paths == ["a/data.bin", "b/data.bin", "c/data.bin"]

    def test_mixed_collisions(self):
        """Some files collide, others don't."""
        files = [
            EcudoFile(name="data.csv", url="https://example.com/raw/data.csv"),
            EcudoFile(name="data.csv", url="https://example.com/processed/data.csv"),
            EcudoFile(name="readme.txt", url="https://example.com/readme.txt"),
        ]

        paths = resolve_path_collisions(files)

        assert paths == ["raw/data.csv", "processed/data.csv", "readme.txt"]
