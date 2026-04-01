"""Tests for URLValidator processor."""

# pylint: disable=missing-function-docstring

import pytest

from crawlers.core.result import Err, Ok
from crawlers.processors import URLValidator


def make_dataset(identifier: str, urls: list[str]):
    """Build a minimal duck-type dataset with given file URLs."""

    class _File:  # pylint: disable=too-few-public-methods
        def __init__(self, url: str):
            self.url = url

    class _Dataset:  # pylint: disable=too-few-public-methods
        def __init__(self, identifier: str, urls: list[str]):
            self.identifier = identifier
            self.files = [_File(u) for u in urls]

    return _Dataset(identifier, urls)


async def valid_url(_url: str):
    return Ok(True)


async def invalid_url(_url: str):
    return Err({"status": 404, "url": _url})


class TestURLValidator:
    """Tests for URLValidator processor."""

    @pytest.mark.asyncio
    async def test_passes_dataset_when_all_urls_valid(self):
        validator = URLValidator(valid_url)
        dataset = make_dataset(
            "ds-1", ["https://example.com/a", "https://example.com/b"]
        )
        result = await validator.process(dataset)
        assert isinstance(result, Ok)
        assert result.value.identifier == "ds-1"

    @pytest.mark.asyncio
    async def test_rejects_dataset_when_url_invalid(self):
        validator = URLValidator(invalid_url)
        dataset = make_dataset("ds-bad", ["https://example.com/missing"])
        result = await validator.process(dataset)
        assert isinstance(result, Err)
        assert result.value["reason"] == "invalid_url"
        assert result.value["dataset_id"] == "ds-bad"
        assert result.value["processor"] == "URLValidator"

    @pytest.mark.asyncio
    async def test_rejects_on_first_invalid_url(self):
        """Stops at the first bad URL — does not check remaining ones."""
        checked: list[str] = []

        async def tracking_fn(url: str):
            checked.append(url)
            if "bad" in url:
                return Err({"status": 404, "url": url})
            return Ok(True)

        dataset = make_dataset(
            "ds-x",
            ["https://example.com/bad", "https://example.com/good"],
        )
        result = await URLValidator(tracking_fn).process(dataset)

        assert isinstance(result, Err)
        assert checked == ["https://example.com/bad"]

    @pytest.mark.asyncio
    async def test_passes_dataset_with_no_files(self):
        validator = URLValidator(invalid_url)
        dataset = make_dataset("ds-empty", [])
        result = await validator.process(dataset)
        assert isinstance(result, Ok)

    @pytest.mark.asyncio
    async def test_stats_processed_incremented_on_pass(self):
        validator = URLValidator(valid_url)
        dataset = make_dataset("ds-1", ["https://example.com/a"])
        await validator.process(dataset)
        await validator.process(make_dataset("ds-2", ["https://example.com/b"]))
        assert validator.stats.processed == 2
        assert validator.stats.filtered == 0

    @pytest.mark.asyncio
    async def test_stats_filtered_incremented_on_reject(self):
        validator = URLValidator(invalid_url)
        await validator.process(make_dataset("ds-1", ["https://example.com/a"]))
        await validator.process(make_dataset("ds-2", ["https://example.com/b"]))
        assert validator.stats.filtered == 2
        assert validator.stats.processed == 0

    @pytest.mark.asyncio
    async def test_error_detail_contains_url(self):
        validator = URLValidator(invalid_url)
        dataset = make_dataset("ds-1", ["https://example.com/404"])
        result = await validator.process(dataset)
        assert isinstance(result, Err)
        assert result.value["detail"]["url"] == "https://example.com/404"
