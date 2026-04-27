"""Tests for the OpenAIRE metadata builder."""

# pylint: disable=redefined-outer-name,missing-function-docstring

import pytest

from crawlers.metadata.openaire import (
    AccessRights,
    BoundingBox,
    FileLocation,
    OpenAIRERecord,
    ResourceType,
)


@pytest.fixture
def sample_record() -> OpenAIRERecord:
    return OpenAIRERecord(
        title="Test Ocean Dataset",
        creator="Institute of Oceanology",
        identifier="urn:SDN:CDI:iopan.pl:uuid:test-123",
        publication_date="2024-01-15",
        access_rights=AccessRights.OPEN,
        resource_type=ResourceType.DATASET,
        language="eng",
        publisher="Institute of Oceanology",
        description="Oceanographic data from research vessel",
        subjects=["ocean", "temperature", "salinity"],
        files=[FileLocation(url="https://example.com/data.zip", mime_type="application/zip")],
        spatial_coverage=BoundingBox(west=18.0, south=54.0, east=19.0, north=55.0),
        temporal_coverage="2024-01-01/2024-01-31",
    )


class TestOpenAIREBuilder:
    """Tests for `OpenAIREBuilder.build`."""

    def test_produces_valid_xml_envelope(self, sample_record):
        result = sample_record.to_xml()
        assert result.startswith("<?xml")
        assert "oaire:resource" in result
        assert result.rstrip().endswith("</oaire:resource>")

    def test_contains_title(self, sample_record):
        result = sample_record.to_xml()
        assert "Test Ocean Dataset" in result
        assert "datacite:title" in result

    def test_contains_identifier(self, sample_record):
        result = sample_record.to_xml()
        assert "urn:SDN:CDI:iopan.pl:uuid:test-123" in result
        assert "datacite:identifier" in result

    def test_contains_publisher(self, sample_record):
        result = sample_record.to_xml()
        assert "Institute of Oceanology" in result
        assert "dc:publisher" in result

    def test_contains_description(self, sample_record):
        result = sample_record.to_xml()
        assert "Oceanographic data from research vessel" in result
        assert "dc:description" in result

    def test_contains_subjects(self, sample_record):
        result = sample_record.to_xml()
        for keyword in ("ocean", "temperature", "salinity"):
            assert f"<datacite:subject>{keyword}</datacite:subject>" in result

    def test_contains_file_location(self, sample_record):
        result = sample_record.to_xml()
        assert "https://example.com/data.zip" in result
        assert "oaire:file" in result
        assert 'mimeType="application/zip"' in result

    def test_contains_geo_location(self, sample_record):
        result = sample_record.to_xml()
        assert "datacite:geoLocationBox" in result
        assert "<datacite:westBoundLongitude>18.0</datacite:westBoundLongitude>" in result
        assert "<datacite:northBoundLatitude>55.0</datacite:northBoundLatitude>" in result

    def test_contains_temporal_coverage(self, sample_record):
        result = sample_record.to_xml()
        assert "2024-01-01/2024-01-31" in result
        assert "dc:coverage" in result

    def test_contains_access_rights(self, sample_record):
        result = sample_record.to_xml()
        assert AccessRights.OPEN.uri in result
        assert "open access" in result

    def test_escapes_special_characters(self):
        record = OpenAIRERecord(
            title="Dataset with <special> & 'characters'",
            creator="Test & Co.",
            identifier="urn:test:123",
            publication_date="2024-01-01",
            access_rights=AccessRights.OPEN,
        )
        result = record.to_xml()
        assert "&lt;special&gt;" in result
        assert "&amp;" in result
        # ElementTree escapes apostrophes only inside attribute values, not text.
        assert "'characters'" in result or "&apos;characters&apos;" in result

    def test_minimal_record_omits_optional_sections(self):
        record = OpenAIRERecord(
            title="Minimal Dataset",
            creator="Anon",
            identifier="urn:test:minimal",
            publication_date="2024-01-01",
            access_rights=AccessRights.OPEN,
        )
        result = record.to_xml()

        assert "Minimal Dataset" in result
        # Optional sections must be absent.
        assert "dc:description" not in result
        assert "dc:publisher" not in result
        assert "dc:language" not in result
        assert "dc:coverage" not in result
        assert "geoLocations" not in result
        assert "datacite:subjects" not in result
        assert "oaire:file" not in result
