"""Tests for OpenAIRESerializer."""

import pytest

from ecudo.models import EcudoRecord, FileInfo
from ecudo.serializers import OpenAIRESerializer


@pytest.fixture
def serializer():
    """Create serializer instance."""
    return OpenAIRESerializer()


@pytest.fixture
def sample_record():
    """Create a sample EcudoRecord for testing."""
    return EcudoRecord(
        identifier="urn:SDN:CDI:iopan.pl:uuid:test-123",
        title="Test Ocean Dataset",
        description="Oceanographic data from research vessel",
        publisher="Institute of Oceanology",
        issued="2024-01-15",
        language="English",
        keywords=["ocean", "temperature", "salinity"],
        files=[
            FileInfo(
                name="data.zip",
                url="https://example.com/data.zip",
                format="WWW:DOWNLOAD",
            )
        ],
        spatial="18.0,54.0,19.0,55.0",
        temporal="2024-01-01/2024-01-31",
    )


class TestOpenAIRESerializer:
    """Tests for OpenAIRESerializer."""

    def test_format_name(self, serializer):
        """Test format_name property."""
        assert serializer.format_name == "OpenAIRE v4.0"

    def test_content_type(self, serializer):
        """Test content_type property."""
        assert serializer.content_type == "application/xml"

    def test_serialize_produces_valid_xml(self, serializer, sample_record):
        """Test that serialize produces valid XML."""
        result = serializer.serialize(sample_record)

        assert result.startswith('<?xml version="1.0" encoding="UTF-8"?>')
        assert "<resource" in result
        assert "</resource>" in result

    def test_serialize_contains_title(self, serializer, sample_record):
        """Test that XML contains title."""
        result = serializer.serialize(sample_record)
        assert "Test Ocean Dataset" in result
        assert "<datacite:title" in result

    def test_serialize_contains_identifier(self, serializer, sample_record):
        """Test that XML contains identifier."""
        result = serializer.serialize(sample_record)
        assert "urn:SDN:CDI:iopan.pl:uuid:test-123" in result
        assert "<datacite:identifier" in result

    def test_serialize_contains_publisher(self, serializer, sample_record):
        """Test that XML contains publisher."""
        result = serializer.serialize(sample_record)
        assert "Institute of Oceanology" in result
        assert "<dc:publisher>" in result

    def test_serialize_contains_description(self, serializer, sample_record):
        """Test that XML contains description."""
        result = serializer.serialize(sample_record)
        assert "Oceanographic data from research vessel" in result
        assert "<dc:description" in result

    def test_serialize_contains_keywords(self, serializer, sample_record):
        """Test that XML contains keywords as subjects."""
        result = serializer.serialize(sample_record)
        assert "<datacite:subject>ocean</datacite:subject>" in result
        assert "<datacite:subject>temperature</datacite:subject>" in result
        assert "<datacite:subject>salinity</datacite:subject>" in result

    def test_serialize_contains_file_location(self, serializer, sample_record):
        """Test that XML contains file location."""
        result = serializer.serialize(sample_record)
        assert "https://example.com/data.zip" in result
        assert "<oaire:file" in result

    def test_serialize_contains_geo_location(self, serializer, sample_record):
        """Test that XML contains geo location."""
        result = serializer.serialize(sample_record)
        assert "<datacite:geoLocationBox>" in result
        assert (
            "<datacite:westBoundLongitude>18.0</datacite:westBoundLongitude>" in result
        )

    def test_serialize_contains_temporal_coverage(self, serializer, sample_record):
        """Test that XML contains temporal coverage."""
        result = serializer.serialize(sample_record)
        assert "2024-01-01/2024-01-31" in result
        assert "<dc:coverage>" in result

    def test_normalize_language_code(self, serializer):
        """Test language code normalization."""
        assert serializer._normalize_language_code("English") == "en"
        assert serializer._normalize_language_code("Polish") == "pl"
        assert serializer._normalize_language_code("en") == "en"
        assert serializer._normalize_language_code("pl") == "pl"
        assert serializer._normalize_language_code("") == "en"
        assert serializer._normalize_language_code("unknown") == "en"

    def test_serialize_escapes_xml_characters(self, serializer):
        """Test that special XML characters are escaped."""
        record = EcudoRecord(
            identifier="urn:test:123",
            title="Dataset with <special> & 'characters'",
            description="",
            publisher="Test & Co.",
            issued="2024-01-01",
            language="en",
            keywords=[],
            files=[FileInfo(name="data.zip", url="https://example.com/data.zip")],
        )
        result = serializer.serialize(record)

        assert "&lt;special&gt;" in result
        assert "&amp;" in result
        assert "&apos;characters&apos;" in result

    def test_serialize_minimal_record(self, serializer):
        """Test serializing a record with minimal fields."""
        record = EcudoRecord(
            identifier="urn:test:minimal",
            title="Minimal Dataset",
            description="",
            publisher="Unknown",
            issued="",
            language="en",
            keywords=[],
            files=[FileInfo(name="data.bin", url="https://example.com/data")],
        )
        result = serializer.serialize(record)

        # Should still produce valid XML
        assert '<?xml version="1.0"' in result
        assert "Minimal Dataset" in result
        assert "</resource>" in result
