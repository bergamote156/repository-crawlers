"""
eCUDO Dataset Record Model

Structured representation of an eCUDO dataset record.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FileInfo:
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
class EcudoRecord:  # pylint: disable=too-many-instance-attributes
    """
    Parsed eCUDO dataset record.

    This is an eCUDO-specific model. When other data sources are added,
    a common interface may be extracted.

    Attributes:
        identifier: Unique identifier (URN format)
        title: Dataset title
        description: Dataset description
        publisher: Publishing organization name
        issued: Publication date (ISO format)
        language: Language code or name
        keywords: List of keywords/subjects
        files: List of downloadable files
        spatial: Optional spatial coverage (bounding box)
        temporal: Optional temporal coverage
        access_level: Access level (e.g., "public", "restricted")
        contact_name: Contact person/organization name (from contactPoint.fn)
        contact_email: Contact email (from contactPoint.hasEmail)
        modified: Last modification date (ISO format)
        _raw: Original raw JSON-LD data (for debugging/extensions)
    """

    identifier: str
    title: str
    description: str
    publisher: str
    issued: str
    language: str
    keywords: List[str]
    files: List[FileInfo]
    spatial: Optional[str] = None
    temporal: Optional[str] = None
    access_level: str = "public"
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    modified: Optional[str] = None

    # Raw data preserved for debugging and future extensions
    _raw: dict = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self):
        """Validate required fields."""
        if not self.identifier:
            raise ValueError("identifier is required")
        if not self.files:
            raise ValueError("at least one file is required")

    def to_json(self) -> dict:
        """Return underlying raw JSON-LD data."""
        return self._raw
