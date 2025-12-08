"""Tests for EcudoParser."""

import pytest

from ecudo.parsers import EcudoParser


@pytest.fixture
def parser():
    """Create parser instance."""
    return EcudoParser()


@pytest.fixture
def valid_record():
    """Sample valid eCUDO JSON-LD record."""
    return {
        "identifier": "urn:SDN:CDI:iopan.pl:uuid:test-123",
        "title": "Test Dataset",
        "description": "A test dataset for unit testing",
        "publisher": {"name": "Test Institute"},
        "issued": "2024-01-15",
        "language": "English",
        "keywords": ["test", "sample", "data"],
        "distribution": [
            {
                "downloadURL": "https://example.com/data/test.zip",
                "format": "WWW:DOWNLOAD-1.0-http--download",
            }
        ],
        "spatial": "18.0,54.0,19.0,55.0",
        "temporal": "2024-01-01/2024-01-31",
    }


class TestEcudoParser:
    """Tests for EcudoParser.parse()."""

    def test_parse_valid_record(self, parser, valid_record):
        """Test parsing a valid record."""
        result = parser.parse(valid_record)

        assert result is not None
        assert result.identifier == "urn:SDN:CDI:iopan.pl:uuid:test-123"
        assert result.title == "Test Dataset"
        assert result.description == "A test dataset for unit testing"
        assert result.publisher == "Test Institute"
        assert result.issued == "2024-01-15"
        assert result.language == "English"
        assert result.keywords == ["test", "sample", "data"]
        assert len(result.files) == 1
        assert result.files[0].url == "https://example.com/data/test.zip"
        assert result.files[0].name == "test.zip"
        assert result.spatial == "18.0,54.0,19.0,55.0"
        assert result.temporal == "2024-01-01/2024-01-31"

    def test_parse_missing_identifier(self, parser):
        """Test that records without identifier are rejected."""
        record = {
            "title": "No ID Dataset",
            "distribution": [{"downloadURL": "https://example.com/data.zip"}],
        }
        result = parser.parse(record)
        assert result is None

    def test_parse_missing_distribution(self, parser):
        """Test that records without distribution are rejected."""
        record = {
            "identifier": "urn:test:123",
            "title": "No Files Dataset",
        }
        result = parser.parse(record)
        assert result is None

    def test_parse_empty_distribution(self, parser):
        """Test that records with empty distribution are rejected."""
        record = {
            "identifier": "urn:test:123",
            "title": "Empty Files Dataset",
            "distribution": [],
        }
        result = parser.parse(record)
        assert result is None

    def test_parse_distribution_without_url(self, parser):
        """Test that distributions without downloadURL are skipped."""
        record = {
            "identifier": "urn:test:123",
            "title": "Bad Distribution",
            "distribution": [{"format": "unknown"}],
        }
        result = parser.parse(record)
        assert result is None

    def test_parse_publisher_as_string(self, parser):
        """Test parsing publisher when it's a string."""
        record = {
            "identifier": "urn:test:123",
            "title": "String Publisher",
            "publisher": "Simple Publisher Name",
            "distribution": [{"downloadURL": "https://example.com/data.zip"}],
        }
        result = parser.parse(record)
        assert result is not None
        assert result.publisher == "Simple Publisher Name"

    def test_parse_missing_publisher(self, parser):
        """Test parsing record without publisher."""
        record = {
            "identifier": "urn:test:123",
            "title": "No Publisher",
            "distribution": [{"downloadURL": "https://example.com/data.zip"}],
        }
        result = parser.parse(record)
        assert result is not None
        assert result.publisher == "Unknown Publisher"

    def test_parse_multiple_files(self, parser):
        """Test parsing record with multiple files."""
        record = {
            "identifier": "urn:test:123",
            "title": "Multi File Dataset",
            "distribution": [
                {"downloadURL": "https://example.com/file1.csv"},
                {"downloadURL": "https://example.com/file2.csv"},
                {"downloadURL": "https://example.com/file3.csv"},
            ],
        }
        result = parser.parse(record)
        assert result is not None
        assert len(result.files) == 3
        assert result.files[0].name == "file1.csv"
        assert result.files[1].name == "file2.csv"
        assert result.files[2].name == "file3.csv"

    def test_parse_preserves_raw(self, parser, valid_record):
        """Test that _raw field preserves original data."""
        result = parser.parse(valid_record)
        assert result is not None
        assert result._raw == valid_record

    def test_extract_filename_from_url(self, parser):
        """Test filename extraction from various URLs."""
        assert (
            parser._extract_filename("https://example.com/path/to/file.zip")
            == "file.zip"
        )
        assert parser._extract_filename("https://example.com/file.csv") == "file.csv"
        assert parser._extract_filename("https://example.com/") == "data.bin"
        assert parser._extract_filename("") == "data.bin"
