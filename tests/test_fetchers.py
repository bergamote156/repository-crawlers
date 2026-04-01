"""Tests for DatasetFetcher processor."""

# pylint: disable=missing-function-docstring

import pytest

from crawlers.core.result import Err, Ok
from crawlers.processors.fetchers import DatasetFetcher


class SimpleParser:  # pylint: disable=too-few-public-methods
    """Parser that wraps raw dict as a dataset-like object."""

    def parse(self, raw: dict) -> dict | None:
        if not raw.get("title"):
            return None
        return raw


async def fetch_ok(dataset_id: str):
    return Ok({"title": f"Dataset {dataset_id}", "id": dataset_id})


async def fetch_fail(_dataset_id: str):
    return Err({"status": 404, "url": "https://example.com/api/ds-999"})


async def fetch_unparseable(_dataset_id: str):
    return Ok({"no_title": True})


class TestDatasetFetcher:
    """Tests for DatasetFetcher processor."""

    @pytest.mark.asyncio
    async def test_returns_ok_on_success(self):
        fetcher = DatasetFetcher(fetch_ok, SimpleParser())
        result = await fetcher.process("ds-1")
        assert isinstance(result, Ok)
        assert result.value["id"] == "ds-1"

    @pytest.mark.asyncio
    async def test_returns_err_when_fetch_fails(self):
        fetcher = DatasetFetcher(fetch_fail, SimpleParser())
        result = await fetcher.process("ds-999")
        assert isinstance(result, Err)
        assert result.value["reason"] == "fetch_failed"
        assert result.value["dataset_id"] == "ds-999"
        assert result.value["processor"] == "DatasetFetcher"

    @pytest.mark.asyncio
    async def test_returns_err_when_parse_fails(self):
        fetcher = DatasetFetcher(fetch_unparseable, SimpleParser())
        result = await fetcher.process("ds-2")
        assert isinstance(result, Err)
        assert result.value["reason"] == "parse_failed"
        assert result.value["dataset_id"] == "ds-2"

    @pytest.mark.asyncio
    async def test_stats_on_success(self):
        fetcher = DatasetFetcher(fetch_ok, SimpleParser())
        await fetcher.process("ds-1")
        await fetcher.process("ds-2")
        assert fetcher.stats.fetched == 2
        assert fetcher.stats.parsed == 2
        assert fetcher.stats.processed == 2
        assert fetcher.stats.failed == 0

    @pytest.mark.asyncio
    async def test_stats_on_fetch_failure(self):
        fetcher = DatasetFetcher(fetch_fail, SimpleParser())
        await fetcher.process("ds-bad")
        assert fetcher.stats.fetched == 0
        assert fetcher.stats.failed == 1
        assert fetcher.stats.processed == 0

    @pytest.mark.asyncio
    async def test_stats_on_parse_failure(self):
        fetcher = DatasetFetcher(fetch_unparseable, SimpleParser())
        await fetcher.process("ds-x")
        assert fetcher.stats.fetched == 1
        assert fetcher.stats.parsed == 0
        assert fetcher.stats.failed == 1

    @pytest.mark.asyncio
    async def test_mixed_results_tracked_independently(self):
        calls = 0

        async def sometimes_fail(dataset_id: str):
            nonlocal calls
            calls += 1
            if dataset_id.startswith("bad"):
                return Err({"status": 500})
            return Ok({"title": f"Dataset {dataset_id}", "id": dataset_id})

        fetcher = DatasetFetcher(sometimes_fail, SimpleParser())
        await fetcher.process("good-1")
        await fetcher.process("bad-1")
        await fetcher.process("good-2")

        assert fetcher.stats.processed == 2
        assert fetcher.stats.failed == 1

    def test_describe_includes_parser_name(self):
        fetcher = DatasetFetcher(fetch_ok, SimpleParser())
        assert "SimpleParser" in fetcher.describe()
