"""Tests for JSONLWriter processor."""

# pylint: disable=redefined-outer-name,protected-access,missing-function-docstring

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from ecudo.processors.writers import JSONLWriter


@dataclass
class SampleItem:
    """Sample item with to_json method."""

    name: str
    value: int

    def to_json(self) -> dict:
        """Convert item to JSON-serializable dict."""
        return {"name": self.name, "value": self.value}


class TestJSONLWriter:
    """Tests for JSONLWriter processor."""

    @pytest.mark.asyncio
    async def test_writes_dict_items(self, tmp_path):
        """Test writing plain dict items."""
        filepath = tmp_path / "output.jsonl"
        writer = JSONLWriter(filepath, show_stats=False)

        await writer.open()
        await writer.process({"a": 1, "b": 2})
        await writer.process({"c": 3, "d": 4})
        await writer.close()

        lines = filepath.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"a": 1, "b": 2}
        assert json.loads(lines[1]) == {"c": 3, "d": 4}

    @pytest.mark.asyncio
    async def test_writes_objects_with_to_json(self, tmp_path):
        """Test writing objects that have to_json() method."""
        filepath = tmp_path / "output.jsonl"
        writer = JSONLWriter(filepath, show_stats=False)

        await writer.open()
        await writer.process(SampleItem("foo", 42))
        await writer.process(SampleItem("bar", 99))
        await writer.close()

        lines = filepath.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"name": "foo", "value": 42}
        assert json.loads(lines[1]) == {"name": "bar", "value": 99}

    @pytest.mark.asyncio
    async def test_returns_same_item(self, tmp_path):
        """Test that process() returns the same item (pass-through)."""
        filepath = tmp_path / "output.jsonl"
        writer = JSONLWriter(filepath, show_stats=False)

        await writer.open()
        item = {"test": "value"}
        result = await writer.process(item)
        await writer.close()

        assert result is item

    @pytest.mark.asyncio
    async def test_creates_parent_directories(self, tmp_path):
        """Test that parent directories are created if they don't exist."""
        filepath = tmp_path / "nested" / "dir" / "output.jsonl"
        writer = JSONLWriter(filepath, show_stats=False)

        await writer.open()
        await writer.process({"data": "test"})
        await writer.close()

        assert filepath.exists()
        assert json.loads(filepath.read_text().strip()) == {"data": "test"}

    @pytest.mark.asyncio
    async def test_appends_to_existing_file(self, tmp_path):
        """Test that writer appends to existing file."""
        filepath = tmp_path / "output.jsonl"

        # First write
        writer1 = JSONLWriter(filepath, show_stats=False)
        await writer1.open()
        await writer1.process({"line": 1})
        await writer1.close()

        # Second write (should append)
        writer2 = JSONLWriter(filepath, show_stats=False)
        await writer2.open()
        await writer2.process({"line": 2})
        await writer2.close()

        lines = filepath.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"line": 1}
        assert json.loads(lines[1]) == {"line": 2}

    @pytest.mark.asyncio
    async def test_raises_error_when_not_opened(self, tmp_path):
        """Test that processing without open() raises error."""
        filepath = tmp_path / "output.jsonl"
        writer = JSONLWriter(filepath, show_stats=False)

        with pytest.raises(RuntimeError, match="Writer not opened"):
            await writer.process({"data": "test"})

    @pytest.mark.asyncio
    async def test_tracks_written_count(self, tmp_path):
        """Test that _written counter is tracked."""
        filepath = tmp_path / "output.jsonl"
        writer = JSONLWriter(filepath, show_stats=False)

        await writer.open()
        assert writer._written == 0

        await writer.process({"a": 1})
        assert writer._written == 1

        await writer.process({"b": 2})
        await writer.process({"c": 3})
        assert writer._written == 3

        await writer.close()

    @pytest.mark.asyncio
    async def test_handles_unicode(self, tmp_path):
        """Test that unicode characters are preserved."""
        filepath = tmp_path / "output.jsonl"
        writer = JSONLWriter(filepath, show_stats=False)

        await writer.open()
        await writer.process({"text": "Zażółć gęślą jaźń"})
        await writer.process({"text": "日本語テスト"})
        await writer.close()

        lines = filepath.read_text(encoding="utf-8").strip().split("\n")
        assert json.loads(lines[0]) == {"text": "Zażółć gęślą jaźń"}
        assert json.loads(lines[1]) == {"text": "日本語テスト"}

    @pytest.mark.asyncio
    async def test_close_without_open_is_safe(self, tmp_path):
        """Test that close() without open() doesn't raise."""
        filepath = tmp_path / "output.jsonl"
        writer = JSONLWriter(filepath, show_stats=False)

        # Should not raise
        await writer.close()

    @pytest.mark.asyncio
    async def test_show_stats_prints_message(self, tmp_path, capsys):
        """Test that show_stats=True prints statistics."""
        filepath = tmp_path / "output.jsonl"
        writer = JSONLWriter(filepath, show_stats=True)

        await writer.open()
        await writer.process({"data": "test"})
        await writer.close()

        captured = capsys.readouterr()
        assert "Wrote 1 items" in captured.out
        assert str(filepath) in captured.out

    @pytest.mark.asyncio
    async def test_accepts_path_object(self, tmp_path):
        """Test that Path objects are accepted."""
        filepath = Path(tmp_path) / "output.jsonl"
        writer = JSONLWriter(filepath, show_stats=False)

        await writer.open()
        await writer.process({"path": "test"})
        await writer.close()

        assert filepath.exists()

    @pytest.mark.asyncio
    async def test_accepts_string_path(self, tmp_path):
        """Test that string paths are accepted."""
        filepath = str(tmp_path / "output.jsonl")
        writer = JSONLWriter(filepath, show_stats=False)

        await writer.open()
        await writer.process({"string": "path"})
        await writer.close()

        assert Path(filepath).exists()
