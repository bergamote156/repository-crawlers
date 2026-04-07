"""Tests for DatasetResolver processor."""

# pylint: disable=missing-function-docstring

import pytest

from crawlers.core.result import Err, Ok
from crawlers.processors.resolvers import DatasetResolver


class SimpleParser:  # pylint: disable=too-few-public-methods
    """Parser that wraps raw dict as a dataset-like object."""

    def parse(self, raw: dict) -> dict | None:
        if not raw.get("title"):
            return None
        return raw


async def resolve_ok(dataset_id: str):
    return Ok({"title": f"Dataset {dataset_id}", "id": dataset_id})


async def resolve_fail(_dataset_id: str):
    return Err({"status": 404, "url": "https://example.com/api/ds-999"})


async def resolve_unparseable(_dataset_id: str):
    return Ok({"no_title": True})


class TestDatasetResolver:
    """Tests for DatasetResolver processor."""

    @pytest.mark.asyncio
    async def test_returns_ok_on_success(self):
        resolver = DatasetResolver(resolve_ok, SimpleParser())
        result = await resolver.process("ds-1")
        assert isinstance(result, Ok)
        assert result.value["id"] == "ds-1"

    @pytest.mark.asyncio
    async def test_returns_err_when_resolve_fails(self):
        resolver = DatasetResolver(resolve_fail, SimpleParser())
        result = await resolver.process("ds-999")
        assert isinstance(result, Err)
        assert result.value["reason"] == "resolve_failed"
        assert result.value["dataset_id"] == "ds-999"
        assert result.value["processor"] == "DatasetResolver"

    @pytest.mark.asyncio
    async def test_returns_err_when_parse_fails(self):
        resolver = DatasetResolver(resolve_unparseable, SimpleParser())
        result = await resolver.process("ds-2")
        assert isinstance(result, Err)
        assert result.value["reason"] == "parse_failed"
        assert result.value["dataset_id"] == "ds-2"

    @pytest.mark.asyncio
    async def test_stats_on_success(self):
        resolver = DatasetResolver(resolve_ok, SimpleParser())
        await resolver.process("ds-1")
        await resolver.process("ds-2")
        assert resolver.stats.resolved == 2
        assert resolver.stats.parsed == 2
        assert resolver.stats.processed == 2
        assert resolver.stats.failed == 0

    @pytest.mark.asyncio
    async def test_stats_on_resolve_failure(self):
        resolver = DatasetResolver(resolve_fail, SimpleParser())
        await resolver.process("ds-bad")
        assert resolver.stats.resolved == 0
        assert resolver.stats.failed == 1
        assert resolver.stats.processed == 0

    @pytest.mark.asyncio
    async def test_stats_on_parse_failure(self):
        resolver = DatasetResolver(resolve_unparseable, SimpleParser())
        await resolver.process("ds-x")
        assert resolver.stats.resolved == 1
        assert resolver.stats.parsed == 0
        assert resolver.stats.failed == 1

    @pytest.mark.asyncio
    async def test_mixed_results_tracked_independently(self):
        calls = 0

        async def sometimes_fail(dataset_id: str):
            nonlocal calls
            calls += 1
            if dataset_id.startswith("bad"):
                return Err({"status": 500})
            return Ok({"title": f"Dataset {dataset_id}", "id": dataset_id})

        resolver = DatasetResolver(sometimes_fail, SimpleParser())
        await resolver.process("good-1")
        await resolver.process("bad-1")
        await resolver.process("good-2")

        assert resolver.stats.processed == 2
        assert resolver.stats.failed == 1

    def test_describe_includes_parser_name(self):
        resolver = DatasetResolver(resolve_ok, SimpleParser())
        assert "SimpleParser" in resolver.describe()

    @pytest.mark.asyncio
    async def test_accepts_dict_input(self):
        """Verify DatasetResolver works with non-string input (e.g. dict)."""

        async def resolve_dict(folder: dict):
            return Ok({"title": folder["name"], "id": folder["_id"]})

        resolver = DatasetResolver(resolve_dict, SimpleParser())
        result = await resolver.process({"_id": "abc123", "name": "Test Folder"})
        assert isinstance(result, Ok)
        assert result.value["id"] == "abc123"

    @pytest.mark.asyncio
    async def test_extract_id_from_dict_input(self):
        """Verify _extract_id handles dict input for error reporting."""

        async def resolve_dict_fail(_folder: dict):
            return Err({"status": 500})

        resolver = DatasetResolver(resolve_dict_fail, SimpleParser())
        result = await resolver.process({"_id": "folder-42", "name": "X"})
        assert isinstance(result, Err)
        assert result.value["dataset_id"] == "folder-42"
