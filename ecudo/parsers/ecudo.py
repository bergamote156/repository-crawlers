"""
eCUDO JSON-LD Parser

Parses raw eCUDO JSON-LD responses into structured EcudoRecord objects.
"""

from typing import Optional
from urllib.parse import urlparse

from ecudo.models.record import EcudoRecord, FileInfo


class EcudoParser:
    """
    Parser for eCUDO JSON-LD metadata.

    Converts raw JSON-LD responses from eCUDO API into structured
    EcudoRecord objects. Handles validation and extraction of nested fields.

    Usage:
        parser = EcudoParser()
        record = parser.parse(raw_json_ld)
        if record:
            # Process valid record
            pass
    """

    def parse(self, raw: dict) -> Optional[EcudoRecord]:
        """
        Parse raw eCUDO JSON-LD to structured EcudoRecord.

        Args:
            raw: Raw JSON-LD dict from eCUDO API

        Returns:
            EcudoRecord if valid, None if record is invalid/incomplete
        """
        # Validate required fields
        identifier = raw.get("identifier")
        if not identifier:
            print("⚠️ Skipping record: missing identifier")
            return None

        distributions = raw.get("distribution", [])
        if not distributions:
            print(f"⚠️ Skipping {identifier}: no distribution URLs")
            return None

        # Parse files from distribution
        files = self._parse_files(distributions)
        if not files:
            print(f"⚠️ Skipping {identifier}: no valid download URLs")
            return None

        # Parse publisher (can be dict or string)
        publisher = self._parse_publisher(raw.get("publisher"))

        # Build and return record
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
            print(f"⚠️ Skipping {identifier}: {e}")
            return None

    def _parse_files(self, distributions: list) -> list[FileInfo]:
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
                    name=self._extract_filename(url),
                    url=url,
                    format=dist.get("format"),
                )
            )

        return files

    @staticmethod
    def _parse_publisher(publisher_data) -> str:
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

    @staticmethod
    def _extract_filename(url: str) -> str:
        """
        Extract filename from URL.

        Args:
            url: Download URL

        Returns:
            Extracted filename or "data.bin" as fallback
        """
        try:
            path = urlparse(url).path
            if path:
                filename = path.split("/")[-1]
                if filename:
                    return filename
        except Exception:
            pass

        return "data.bin"
