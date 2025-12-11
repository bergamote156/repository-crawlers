"""
eCUDO Dataset Metadata Model

Structured representation of an eCUDO dataset metadata.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class EcudoFile:
    """
    Information about a downloadable file in a dataset.

    Attributes:
        name: Filename (extracted from URL or provided)
        url: Download URL
        format: Optional format identifier (e.g., "WWW:DOWNLOAD-1.0-http--download")
    """

    name: str
    url: str
    format: Optional[str] = None


@dataclass
class EcudoDataset:  # pylint: disable=too-many-instance-attributes
    """
    Parsed eCUDO dataset record.

    This is an eCUDO-specific model. When other data sources are added,
    a common interface may be extracted.

    Attributes:
        identifier: Unique identifier (URN format)
        title: Dataset title
        description: Dataset description
        publisher: Publishing organization name
        language: Language code or name
        keywords: List of keywords/subjects
        files: List of downloadable files
        issued: Publication date (ISO format)
        modified: Last modification date (ISO format)
        spatial: Optional spatial coverage (bounding box)
        temporal: Optional temporal coverage
        access_level: Access level (e.g., "public", "restricted")
        _raw: Original raw JSON-LD data (for debugging/extensions)
    """

    identifier: str
    title: str
    description: str
    publisher: str
    language: str
    keywords: List[str]
    files: List[EcudoFile]
    issued: str
    modified: Optional[str] = None
    spatial: Optional[str] = None
    temporal: Optional[str] = None
    access_level: str = "public"

    # Raw data preserved for debugging and future extensions
    _raw: dict = field(default_factory=dict, repr=False, compare=False)

    def to_json(self) -> dict:
        """Return underlying raw JSON-LD data."""
        return self._raw
