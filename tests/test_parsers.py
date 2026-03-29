"""Tests for ParserProcessor."""

# pylint: disable=missing-function-docstring,protected-access

import pytest

from crawlers.core.processors.parsers import ParserProcessor
from crawlers.core.result import Ok


class SuccessParser:  # pylint: disable=too-few-public-methods
    """Parser that always succeeds."""

    def parse(self, raw: dict) -> str:
        return raw.get("title", "unknown")


class FailParser:  # pylint: disable=too-few-public-methods
    """Parser that always returns None (failed parse)."""

    def parse(self, _raw: dict) -> None:
        return None


class TestParserProcessor:
    """Tests for ParserProcessor."""

    @pytest.mark.asyncio
    async def test_returns_ok_on_success(self):
        processor = ParserProcessor(SuccessParser())
        result = await processor.process({"title": "My Dataset"})
        assert result == Ok("My Dataset")

    @pytest.mark.asyncio
    async def test_returns_err_on_failed_parse(self):
        processor = ParserProcessor(FailParser())
        result = await processor.process({"id": "ds-1"})
        assert result.is_err()
        err = result.err()
        assert err["reason"] == "parse_failed"
        assert err["processor"] == "ParserProcessor"

    @pytest.mark.asyncio
    async def test_stats_processed_incremented_on_success(self):
        processor = ParserProcessor(SuccessParser())
        await processor.process({"title": "A"})
        await processor.process({"title": "B"})
        assert processor.stats.processed == 2
        assert processor.stats.failed == 0

    @pytest.mark.asyncio
    async def test_stats_failed_incremented_on_failure(self):
        processor = ParserProcessor(FailParser())
        await processor.process({"id": "x"})
        await processor.process({"id": "y"})
        assert processor.stats.failed == 2
        assert processor.stats.processed == 0

    @pytest.mark.asyncio
    async def test_stats_parsed_incremented_on_success(self):
        processor = ParserProcessor(SuccessParser())
        await processor.process({"title": "A"})
        assert processor.stats.parsed == 1

    @pytest.mark.asyncio
    async def test_describe_includes_parser_name(self):
        processor = ParserProcessor(SuccessParser())
        assert "SuccessParser" in processor.describe()

    def test_extract_id_from_dict_id_key(self):
        processor = ParserProcessor(SuccessParser())
        assert processor._extract_id({"id": "abc-123"}) == "abc-123"

    def test_extract_id_from_dict_identifier_key(self):
        processor = ParserProcessor(SuccessParser())
        assert processor._extract_id({"identifier": "urn:test:1"}) == "urn:test:1"

    def test_extract_id_from_string(self):
        processor = ParserProcessor(SuccessParser())
        assert processor._extract_id("raw-id-string") == "raw-id-string"

    def test_extract_id_unknown_returns_unknown(self):
        processor = ParserProcessor(SuccessParser())
        assert processor._extract_id({}) == "unknown"

    def test_extract_id_non_dict_non_str(self):
        processor = ParserProcessor(SuccessParser())
        assert processor._extract_id(42) == "unknown"
