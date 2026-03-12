"""Tests for parser utilities."""

# pylint: disable=redefined-outer-name,protected-access,missing-function-docstring

import pytest

from crawlers.plugins.ecudo.parser import (
    EcudoParser,
    extract_filename,
    parse_files,
    parse_publisher,
)


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


class TestParseRecord:
    """Tests for parse_record()."""

    def test_parse_valid_record(self, valid_record):
        """Test parsing a valid record."""
        parser = EcudoParser()
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

    def test_parse_missing_identifier(self):
        """Test that records without identifier are rejected."""
        record = {
            "title": "No ID Dataset",
            "distribution": [{"downloadURL": "https://example.com/data.zip"}],
        }
        parser = EcudoParser()
        result = parser.parse(record)
        assert result is None

    def test_parse_missing_distribution(self):
        """Test that records without distribution are rejected."""
        record = {
            "identifier": "urn:test:123",
            "title": "No Files Dataset",
        }
        parser = EcudoParser()
        result = parser.parse(record)
        assert result is None

    def test_parse_empty_distribution(self):
        """Test that records with empty distribution are rejected."""
        record = {
            "identifier": "urn:test:123",
            "title": "Empty Files Dataset",
            "distribution": [],
        }
        parser = EcudoParser()
        result = parser.parse(record)
        assert result is None

    def test_parse_distribution_without_url(self):
        """Test that distributions without downloadURL are skipped."""
        record = {
            "identifier": "urn:test:123",
            "title": "Bad Distribution",
            "distribution": [{"format": "unknown"}],
        }
        parser = EcudoParser()
        result = parser.parse(record)
        assert result is None

    def test_parse_publisher_as_string(self):
        """Test parsing publisher when it's a string."""
        record = {
            "identifier": "urn:test:123",
            "title": "String Publisher",
            "publisher": "Simple Publisher Name",
            "distribution": [{"downloadURL": "https://example.com/data.zip"}],
        }
        parser = EcudoParser()
        result = parser.parse(record)
        assert result is not None
        assert result.publisher == "Simple Publisher Name"

    def test_parse_missing_publisher(self):
        """Test parsing record without publisher."""
        record = {
            "identifier": "urn:test:123",
            "title": "No Publisher",
            "distribution": [{"downloadURL": "https://example.com/data.zip"}],
        }
        parser = EcudoParser()
        result = parser.parse(record)
        assert result is not None
        assert result.publisher == "Unknown Publisher"

    def test_parse_multiple_files(self):
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
        parser = EcudoParser()
        result = parser.parse(record)
        assert result is not None
        assert len(result.files) == 3
        assert result.files[0].name == "file1.csv"
        assert result.files[1].name == "file2.csv"
        assert result.files[2].name == "file3.csv"

    def test_parse_preserves_raw(self, valid_record):
        """Test that _raw field preserves original data."""
        parser = EcudoParser()
        result = parser.parse(valid_record)
        assert result is not None
        assert result._raw == valid_record

    def test_extract_filename_from_url(self):
        """Test filename extraction from various URLs."""
        assert extract_filename("https://example.com/path/to/file.zip") == "file.zip"
        assert extract_filename("https://example.com/file.csv") == "file.csv"
        assert extract_filename("https://example.com/") == "data.bin"
        assert extract_filename("") == "data.bin"


class TestParseFiles:
    """Tests for parse_files() function."""

    def test_parse_single_distribution(self):
        """Test parsing a single distribution."""
        distributions = [
            {"downloadURL": "https://example.com/data.zip", "format": "WWW:DOWNLOAD"}
        ]
        files = parse_files(distributions)

        assert len(files) == 1
        assert files[0].name == "data.zip"
        assert files[0].url == "https://example.com/data.zip"

    def test_parse_multiple_distributions(self):
        """Test parsing multiple distributions."""
        distributions = [
            {"downloadURL": "https://example.com/file1.csv"},
            {"downloadURL": "https://example.com/file2.csv"},
            {"downloadURL": "https://example.com/file3.csv"},
        ]
        files = parse_files(distributions)

        assert len(files) == 3
        assert files[0].name == "file1.csv"
        assert files[1].name == "file2.csv"
        assert files[2].name == "file3.csv"

    def test_skip_distributions_without_url(self):
        """Test that distributions without downloadURL are skipped."""
        distributions = [
            {"downloadURL": "https://example.com/valid.zip"},
            {"format": "unknown"},  # No URL
            {"downloadURL": "https://example.com/another.zip"},
        ]
        files = parse_files(distributions)

        assert len(files) == 2
        assert files[0].name == "valid.zip"
        assert files[1].name == "another.zip"

    def test_empty_distributions(self):
        """Test parsing empty distribution list."""
        files = parse_files([])
        assert not files

    def test_format_is_optional(self):
        """Test that format field is optional."""
        distributions = [{"downloadURL": "https://example.com/data.bin"}]
        files = parse_files(distributions)

        assert len(files) == 1


class TestParsePublisher:
    """Tests for parse_publisher() function."""

    def test_publisher_as_dict(self):
        """Test parsing publisher when it's a dict with name."""
        publisher_data = {
            "name": "Institute of Oceanology",
            "@type": "org:Organization",
        }
        result = parse_publisher(publisher_data)
        assert result == "Institute of Oceanology"

    def test_publisher_as_string(self):
        """Test parsing publisher when it's a plain string."""
        publisher_data = "Simple Publisher Name"
        result = parse_publisher(publisher_data)
        assert result == "Simple Publisher Name"

    def test_publisher_none(self):
        """Test parsing when publisher is None."""
        result = parse_publisher(None)
        assert result == "Unknown Publisher"

    def test_publisher_empty_string(self):
        """Test parsing when publisher is empty string."""
        result = parse_publisher("")
        assert result == "Unknown Publisher"

    def test_publisher_dict_without_name(self):
        """Test parsing publisher dict without name field."""
        publisher_data = {"@type": "org:Organization"}
        result = parse_publisher(publisher_data)
        assert result == "Unknown Publisher"


class TestExtractFilename:
    """Extended tests for extract_filename() function."""

    def test_simple_url(self):
        """Test extracting filename from simple URL."""
        assert extract_filename("https://example.com/data.csv") == "data.csv"

    def test_deep_path(self):
        """Test extracting filename from deep URL path."""
        url = "https://databank.iopan.pl/data/raw/vdr/vdr_201307_201312_nmea-08895.zip"
        assert extract_filename(url) == "vdr_201307_201312_nmea-08895.zip"

    def test_url_with_query_string(self):
        """Test extracting filename ignores query string."""
        url = "https://example.com/path/file.zip?token=abc123"
        result = extract_filename(url)
        # The current implementation includes query string in filename
        assert result == "file.zip"

    def test_url_without_extension(self):
        """Test extracting filename without extension."""
        url = "https://example.com/api/data/23"
        assert extract_filename(url) == "23"

    def test_empty_url(self):
        """Test fallback for empty URL."""
        assert extract_filename("") == "data.bin"

    def test_root_url(self):
        """Test fallback for URL with just root path."""
        assert extract_filename("https://example.com/") == "data.bin"

    def test_url_ending_with_slash(self):
        """Test URL ending with slash."""
        assert extract_filename("https://example.com/path/") == "data.bin"
