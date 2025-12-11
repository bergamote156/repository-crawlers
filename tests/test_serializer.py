"""Tests for OpenAIRE metadata generator."""

import pytest

from ecudo.metadata import openaire
from ecudo.models import EcudoDataset, EcudoFile


@pytest.fixture
def sample_record():
    """Create a sample EcudoRecord for testing."""
    return EcudoDataset(
        identifier="urn:SDN:CDI:iopan.pl:uuid:test-123",
        title="Test Ocean Dataset",
        description="Oceanographic data from research vessel",
        publisher="Institute of Oceanology",
        issued="2024-01-15",
        language="English",
        keywords=["ocean", "temperature", "salinity"],
        files=[
            EcudoFile(
                name="data.zip",
                url="https://example.com/data.zip",
                format="WWW:DOWNLOAD",
            )
        ],
        spatial="18.0,54.0,19.0,55.0",
        temporal="2024-01-01/2024-01-31",
    )


class TestOpenAIREMetadata:
    """Tests for OpenAIRE metadata generator."""

    def test_format_constants(self):
        """Test format name and content type constants."""
        assert openaire.FORMAT_NAME == "OpenAIRE v4.0"
        assert openaire.CONTENT_TYPE == "application/xml"

    def test_generate_xml_produces_valid_xml(self, sample_record):
        """Test that generate_xml produces valid XML."""
        result = openaire.generate_xml(sample_record)

        assert result.startswith('<?xml version="1.0" encoding="UTF-8"?>')
        assert "<oaire:resource" in result
        assert "</oaire:resource>" in result

    def test_generate_xml_contains_title(self, sample_record):
        """Test that XML contains title."""
        result = openaire.generate_xml(sample_record)
        assert "Test Ocean Dataset" in result
        assert "<datacite:title" in result

    def test_generate_xml_contains_identifier(self, sample_record):
        """Test that XML contains identifier."""
        result = openaire.generate_xml(sample_record)
        assert "urn:SDN:CDI:iopan.pl:uuid:test-123" in result
        assert "<datacite:identifier" in result

    def test_generate_xml_contains_publisher(self, sample_record):
        """Test that XML contains publisher."""
        result = openaire.generate_xml(sample_record)
        assert "Institute of Oceanology" in result
        assert "<dc:publisher>" in result

    def test_generate_xml_contains_description(self, sample_record):
        """Test that XML contains description."""
        result = openaire.generate_xml(sample_record)
        assert "Oceanographic data from research vessel" in result
        assert "<dc:description" in result

    def test_generate_xml_contains_keywords(self, sample_record):
        """Test that XML contains keywords as subjects."""
        result = openaire.generate_xml(sample_record)
        assert "<datacite:subject>ocean</datacite:subject>" in result
        assert "<datacite:subject>temperature</datacite:subject>" in result
        assert "<datacite:subject>salinity</datacite:subject>" in result

    def test_generate_xml_contains_file_location(self, sample_record):
        """Test that XML contains file location."""
        result = openaire.generate_xml(sample_record)
        assert "https://example.com/data.zip" in result
        assert "<oaire:file" in result

    def test_generate_xml_contains_geo_location(self, sample_record):
        """Test that XML contains geo location."""
        result = openaire.generate_xml(sample_record)
        assert "<datacite:geoLocationBox>" in result
        assert (
            "<datacite:westBoundLongitude>18.0</datacite:westBoundLongitude>" in result
        )

    def test_generate_xml_contains_temporal_coverage(self, sample_record):
        """Test that XML contains temporal coverage."""
        result = openaire.generate_xml(sample_record)
        assert "2024-01-01/2024-01-31" in result
        assert "<dc:coverage>" in result

    def test_normalize_language_code(self):
        """Test language code normalization."""
        assert openaire._normalize_language_code("English") == "en"
        assert openaire._normalize_language_code("Polish") == "pl"
        assert openaire._normalize_language_code("en") == "en"
        assert openaire._normalize_language_code("pl") == "pl"
        assert openaire._normalize_language_code("") == "en"
        assert openaire._normalize_language_code("unknown") == "en"

    def test_generate_xml_escapes_xml_characters(self):
        """Test that special XML characters are escaped."""
        record = EcudoDataset(
            identifier="urn:test:123",
            title="Dataset with <special> & 'characters'",
            description="",
            publisher="Test & Co.",
            issued="2024-01-01",
            language="en",
            keywords=[],
            files=[EcudoFile(name="data.zip", url="https://example.com/data.zip")],
        )
        result = openaire.generate_xml(record)

        assert "&lt;special&gt;" in result
        assert "&amp;" in result
        assert "&apos;characters&apos;" in result

    def test_generate_xml_minimal_record(self):
        """Test generating XML for a record with minimal fields."""
        record = EcudoDataset(
            identifier="urn:test:minimal",
            title="Minimal Dataset",
            description="",
            publisher="Unknown",
            issued="",
            language="en",
            keywords=[],
            files=[EcudoFile(name="data.bin", url="https://example.com/data")],
        )
        result = openaire.generate_xml(record)

        # Should still produce valid XML
        assert '<?xml version="1.0"' in result
        assert "Minimal Dataset" in result
        assert "</oaire:resource>" in result
