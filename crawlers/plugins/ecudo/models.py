"""
Ecudo Data Models.
"""

from dataclasses import dataclass, field


@dataclass
class EcudoFile:
    """File from Ecudo dataset."""

    name: str
    url: str


@dataclass
class EcudoDataset:
    """Ecudo Dataset model."""

    identifier: str
    title: str
    description: str
    publisher: str
    issued: str  # publication date
    files: list[EcudoFile]

    # Optional but common fields
    language: str = "en"
    keywords: list[str] = field(default_factory=list)
    modified: str | None = None
    access_level: str = "public"

    # Geographic/temporal metadata
    spatial: str | None = None
    temporal: str | None = None

    # Raw JSON-LD data from API
    _raw: dict = field(default_factory=dict, repr=False, compare=False)

    def to_json(self) -> dict:
        """Return the raw JSON-LD data."""
        return self._raw
