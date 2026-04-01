"""Tests for JSONLSink and NullSink."""

# pylint: disable=missing-function-docstring

import json
from pathlib import Path

import pytest

from crawlers.sinks import JSONLSink, NullSink


class TestJSONLSink:
    """Tests for JSONLSink."""

    @pytest.mark.asyncio
    async def test_writes_json_line(self, tmp_path):
        path = tmp_path / "out.jsonl"
        data = {"id": "1", "title": "Test"}

        sink = JSONLSink(path)
        await sink.open()
        await sink.push(data)
        await sink.close()

        assert load_jsonl(path) == [data]

    @pytest.mark.asyncio
    async def test_writes_multiple_lines(self, tmp_path):
        path = tmp_path / "out.jsonl"
        data1 = {"id": "1"}
        data2 = {"id": "2"}
        data3 = {"id": "3"}

        sink = JSONLSink(path)
        await sink.open()
        await sink.push(data1)
        await sink.push(data2)
        await sink.push(data3)
        await sink.close()

        assert load_jsonl(path) == [data1, data2, data3]

    @pytest.mark.asyncio
    async def test_appends_on_reopen(self, tmp_path):
        """Reopening in append mode keeps existing data."""
        path = tmp_path / "out.jsonl"
        data1 = {"id": "first"}
        data2 = {"id": "second"}

        sink = JSONLSink(path)
        await sink.open()
        await sink.push(data1)
        await sink.close()

        sink2 = JSONLSink(path)
        await sink2.open()
        await sink2.push(data2)
        await sink2.close()

        assert load_jsonl(path) == [data1, data2]

    @pytest.mark.asyncio
    async def test_creates_parent_directories(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "out.jsonl"
        sink = JSONLSink(path)
        await sink.open()
        await sink.push({"x": 1})
        await sink.close()
        assert path.exists()

    @pytest.mark.asyncio
    async def test_handles_non_ascii_characters(self, tmp_path):
        path = tmp_path / "out.jsonl"
        data = {"title": "Zbiór danych — łódź"}

        sink = JSONLSink(path)
        await sink.open()
        await sink.push(data)
        await sink.close()

        assert load_jsonl(path) == [data]

    def test_artifacts_returns_path(self, tmp_path):
        path = tmp_path / "out.jsonl"
        sink = JSONLSink(path)
        assert sink.artifacts() == [path]


def load_jsonl(path):
    return list(map(json.loads, Path(path).read_text(encoding="utf-8").splitlines()))
