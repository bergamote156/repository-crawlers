"""Tests for resolve_path_collisions util."""

# pylint: disable=missing-function-docstring

from crawlers.plugins.utils.paths import resolve_path_collisions


def test_empty_list():
    assert resolve_path_collisions([]) == []


def test_single_file():
    assert resolve_path_collisions(["https://example.com/data.csv"]) == ["data.csv"]


def test_no_collisions():
    paths = resolve_path_collisions(
        [
            "https://example.com/a/data.csv",
            "https://example.com/b/readme.txt",
        ]
    )
    assert paths == ["data.csv", "readme.txt"]


def test_simple_collision():
    paths = resolve_path_collisions(
        [
            "https://example.com/raw/data.csv",
            "https://example.com/processed/data.csv",
        ]
    )
    assert paths == ["raw/data.csv", "processed/data.csv"]


def test_deep_collision():
    paths = resolve_path_collisions(
        [
            "https://example.com/api/stats/hl/2013/2/23",
            "https://example.com/api/data/hl/2013/2/23",
        ]
    )
    assert paths == ["stats/hl/2013/2/23", "data/hl/2013/2/23"]


def test_multiple_collisions():
    paths = resolve_path_collisions(
        [
            "https://example.com/a/data.bin",
            "https://example.com/b/data.bin",
            "https://example.com/c/data.bin",
        ]
    )
    assert paths == ["a/data.bin", "b/data.bin", "c/data.bin"]


def test_mixed_collisions():
    paths = resolve_path_collisions(
        [
            "https://example.com/raw/data.csv",
            "https://example.com/processed/data.csv",
            "https://example.com/readme.txt",
        ]
    )
    assert paths == ["raw/data.csv", "processed/data.csv", "readme.txt"]


def test_query_string_stripped():
    assert resolve_path_collisions(["https://example.com/path/file.zip?token=abc123"]) == [
        "file.zip"
    ]


def test_root_url_fallback():
    assert resolve_path_collisions(["https://example.com/"]) == ["data.bin"]
