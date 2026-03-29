"""Tests for JSONLSink and NullSink."""

# pylint: disable=missing-function-docstring

import json

import pytest

from crawlers.core.sinks import JSONLSink, NullSink


class TestJSONLSink:
    """Tests for JSONLSink."""

    @pytest.mark.asyncio
    async def test_writes_json_line(self, tmp_path):
        path = tmp_path / "out.jsonl"
        sink = JSONLSink(path)
        await sink.open()
        await sink.push({"id": "1", "title": "Test"})
        await sink.close()

        lines = path.read_text().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0]) == {"id": "1", "title": "Test"}

    @pytest.mark.asyncio
    async def test_writes_multiple_lines(self, tmp_path):
        path = tmp_path / "out.jsonl"
        sink = JSONLSink(path)
        await sink.open()
        await sink.push({"id": "1"})
        await sink.push({"id": "2"})
        await sink.push({"id": "3"})
        await sink.close()

        lines = path.read_text().splitlines()
        assert len(lines) == 3
        assert json.loads(lines[2]) == {"id": "3"}

    @pytest.mark.asyncio
    async def test_appends_on_reopen(self, tmp_path):
        """Reopening in append mode keeps existing data."""
        path = tmp_path / "out.jsonl"

        sink = JSONLSink(path)
        await sink.open()
        await sink.push({"id": "first"})
        await sink.close()

        sink2 = JSONLSink(path)
        await sink2.open()
        await sink2.push({"id": "second"})
        await sink2.close()

        lines = path.read_text().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["id"] == "first"
        assert json.loads(lines[1])["id"] == "second"

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
        sink = JSONLSink(path)
        await sink.open()
        await sink.push({"title": "Zbiór danych — łódź"})
        await sink.close()

        line = json.loads(path.read_text(encoding="utf-8").strip())
        assert line["title"] == "Zbiór danych — łódź"

    def test_artifacts_returns_path(self, tmp_path):
        path = tmp_path / "out.jsonl"
        sink = JSONLSink(path)
        assert sink.artifacts() == [path]

    def test_repr(self, tmp_path):
        path = tmp_path / "out.jsonl"
        sink = JSONLSink(path)
        assert "JSONLSink" in repr(sink)
        assert str(path) in repr(sink)


class TestNullSink:
    """Tests for NullSink."""

    @pytest.mark.asyncio
    async def test_open_does_nothing(self):
        sink = NullSink()
        await sink.open()  # Should not raise

    @pytest.mark.asyncio
    async def test_push_discards_data(self):
        sink = NullSink()
        await sink.open()
        await sink.push({"data": "ignored"})
        await sink.close()
        # No assertions needed — just must not raise

    @pytest.mark.asyncio
    async def test_close_does_nothing(self):
        sink = NullSink()
        await sink.close()  # Should not raise even without open

    def test_artifacts_empty(self):
        assert not NullSink().artifacts()

    def test_repr(self):
        assert repr(NullSink()) == "NullSink()"
