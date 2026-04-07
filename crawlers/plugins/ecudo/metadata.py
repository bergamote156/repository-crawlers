"""
Ecudo OpenAIRE metadata adapter.

Maps :class:`EcudoDataset` (parsed JSON-LD) onto :class:`OpenAIRERecord`,
and exposes a :class:`MetadataBuilder[EcudoDataset]` so the converter
pipeline can stay generic.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from crawlers.core.metadata import MetadataBuilder
from crawlers.metadata.openaire import (
    AccessRights,
    BoundingBox,
    FileLocation,
    OpenAIREBuilder,
    OpenAIRERecord,
    ResourceType,
)
from crawlers.plugins.ecudo.parser import EcudoDataset
from crawlers.plugins.utils.language import normalize_language_code
from crawlers.plugins.utils.mime import infer_mime_type
from crawlers.ui import console

# Maps eCUDO ``accessLevel`` strings to COAR access right enums. Extend as new
# values are encountered in the wild.
_ACCESS_LEVEL_MAP: dict[str, AccessRights] = {
    "public": AccessRights.OPEN,
}


class EcudoOpenAIREBuilder(MetadataBuilder[EcudoDataset]):
    """Adapter exposing OpenAIRE XML generation as a builder over EcudoDataset."""

    def __init__(self) -> None:
        self._builder = OpenAIREBuilder()

    def build(self, dataset: EcudoDataset) -> str:
        return self._builder.build(ecudo_to_openaire_record(dataset))


def ecudo_to_openaire_record(dataset: EcudoDataset) -> OpenAIRERecord:
    """Convert an :class:`EcudoDataset` into an :class:`OpenAIRERecord`."""
    return OpenAIRERecord(
        title=dataset.title,
        creator=dataset.publisher,
        identifier=dataset.identifier,
        publication_date=dataset.issued,
        access_rights=_resolve_access_rights(dataset.access_level),
        resource_type=ResourceType.DATASET,
        language=normalize_language_code(dataset.language),
        publisher=dataset.publisher,
        description=dataset.description or None,
        subjects=list(dataset.keywords),
        files=[
            FileLocation(url=f.url, mime_type=infer_mime_type(f.url))
            for f in dataset.files
        ],
        temporal_coverage=dataset.temporal,
        spatial_coverage=_parse_bounding_box(dataset.spatial),
    )


def _resolve_access_rights(level: str | None) -> AccessRights:
    if level and level in _ACCESS_LEVEL_MAP:
        return _ACCESS_LEVEL_MAP[level]

    if level:
        console.warning(
            f"Unknown eCUDO accessLevel '{level}', defaulting to open access."
        )

    return AccessRights.OPEN


def _parse_bounding_box(spatial: str | None) -> BoundingBox | None:
    """Parse an eCUDO ``spatial`` string ("west,south,east,north")."""
    if not spatial:
        return None
    try:
        coords = [float(x.strip()) for x in spatial.split(",")]
    except ValueError:
        console.warning(f"Could not parse spatial coordinates '{spatial}'")
        return None

    if len(coords) != 4:
        console.warning(
            f"Expected 4 spatial coordinates, got {len(coords)}: '{spatial}'"
        )
        return None

    west, south, east, north = coords
    return BoundingBox(west=west, south=south, east=east, north=north)
