"""Tests for OnedataConverter."""

# pylint: disable=redefined-outer-name,protected-access,missing-function-docstring

import pytest

from crawlers.core.result import Err
from crawlers.metadata.openaire import (
    AccessRights,
    OpenAIREBuilder,
    OpenAIRERecord,
    ResourceType,
)
from crawlers.plugins.ecudo.parser import EcudoDataset, EcudoFile
from crawlers.processors.converters import OnedataConverter


def _make_record(
    identifier: str = "urn:SDN:CDI:iopan.pl:uuid:test-123",
    title: str = "Test Dataset / With Slash",
    files: list[EcudoFile] | None = None,
) -> EcudoDataset:
    if files is None:
        files = [
            EcudoFile(path="data.csv", url="https://example.com/data.csv"),
            EcudoFile(path="readme.txt", url="https://example.com/readme.txt"),
        ]
    return EcudoDataset(
        identifier=identifier,
        title=title,
        files=files,
        metadata_record=OpenAIRERecord(
            title=title,
            creator="Test Institute",
            identifier=identifier,
            publication_date="2024-01-15",
            access_rights=AccessRights.OPEN,
            resource_type=ResourceType.DATASET,
            language="eng",
            publisher="Test Institute",
            description="Test description",
            subjects=["test"],
        ),
    )


@pytest.fixture
def converter():
    return OnedataConverter(OpenAIREBuilder())


@pytest.fixture
def sample_record():
    return _make_record()


class TestOnedataConverter:
    """Tests for OnedataConverter."""

    @pytest.mark.asyncio
    async def test_converts_record(self, converter, sample_record):
        result = await converter.process(sample_record)
        dataset = result.value

        assert dataset.name == "Test Dataset / With Slash"
        assert dataset.location == "Test Dataset - With Slash"
        assert dataset.pid == "urn:SDN:CDI:iopan.pl:uuid:test-123"

    @pytest.mark.asyncio
    async def test_generates_metadata_xml(self, converter, sample_record):
        dataset = (await converter.process(sample_record)).value

        assert dataset.metadata_xml.startswith("<?xml version='1.0'")
        assert "Test Dataset" in dataset.metadata_xml

    @pytest.mark.asyncio
    async def test_converts_files(self, converter, sample_record):
        dataset = (await converter.process(sample_record)).value

        assert len(dataset.files) == 2
        assert dataset.files[0].path == "data.csv"
        assert dataset.files[0].url == "https://example.com/data.csv"

    @pytest.mark.asyncio
    async def test_to_json(self, converter, sample_record):
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
        record = _make_record(
            identifier="urn:test:dup",
            title="Dup",
            files=[
                EcudoFile(path="data.csv", url="https://a.example/data.csv"),
                EcudoFile(path="data.csv", url="https://b.example/data.csv"),
            ],
        )

        result = await converter.process(record)

        assert isinstance(result, Err)
        assert result.value["reason"] == "duplicate_file_paths"
        assert result.value["detail"]["paths"] == ["data.csv"]
