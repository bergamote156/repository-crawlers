"""Utilities for parsing eCUDO JSON-LD responses into EcudoRecord objects."""

from contextlib import suppress
from typing import Optional
from urllib.parse import urlparse

from ecudo import output
from ecudo.models.record import EcudoRecord, FileInfo


def parse_record(raw: dict) -> Optional[EcudoRecord]:
    """
    Parse raw eCUDO JSON-LD to structured EcudoRecord.

    Args:
        raw: Raw JSON-LD dict from eCUDO API

    Returns:
        EcudoRecord if valid, None if record is invalid/incomplete
    """
    identifier = raw.get("identifier")
    if not identifier:
        output.debug("⚠️ Skipping record: missing identifier")
        return None

    distributions = raw.get("distribution", [])
    if not distributions:
        output.debug(f"⚠️ Skipping {identifier}: no distribution URLs")
        return None

    files = parse_files(distributions)
    if not files:
        output.debug(f"⚠️ Skipping {identifier}: no valid download URLs")
        return None

    publisher = parse_publisher(raw.get("publisher"))

    try:
        return EcudoRecord(
            identifier=identifier,
            title=raw.get("title", "Untitled Dataset"),
            description=raw.get("description", ""),
            publisher=publisher,
            issued=raw.get("issued", raw.get("modified", "")),
            language=raw.get("language", "en"),
            keywords=raw.get("keywords", []),
            files=files,
            spatial=raw.get("spatial"),
            temporal=raw.get("temporal"),
            _raw=raw,
        )
    except ValueError as e:
        output.debug(f"⚠️ Skipping {identifier}: {e}")
        return None


def parse_files(distributions: list) -> list[FileInfo]:
    """
    Parse distribution array into FileInfo list.

    Args:
        distributions: List of distribution dicts from JSON-LD

    Returns:
        List of FileInfo objects (may be empty)
    """
    files = []
    for dist in distributions:
        url = dist.get("downloadURL")
        if not url:
            continue

        files.append(
            FileInfo(
                name=extract_filename(url),
                url=url,
                format=dist.get("format"),
            )
        )

    return files


def parse_publisher(publisher_data) -> str:
    """
    Parse publisher field which can be dict or string.

    Args:
        publisher_data: Publisher field from JSON-LD (dict, str, or None)

    Returns:
        Publisher name string
    """
    if not publisher_data:
        return "Unknown Publisher"

    if isinstance(publisher_data, dict):
        return publisher_data.get("name", "Unknown Publisher")

    if isinstance(publisher_data, str):
        return publisher_data

    return "Unknown Publisher"


def extract_filename(url: str) -> str:
    """
    Extract filename from URL.

    Args:
        url: Download URL

    Returns:
        Extracted filename or "data.bin" as fallback
    """
    with suppress(ValueError, AttributeError, TypeError):
        path = urlparse(url).path
        if path:
            filename = path.split("/")[-1]
            if filename:
                return filename

    # Gracefully fall through to default filename
    return "data.bin"
