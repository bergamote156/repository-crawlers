# Metadata Generation

## Overview

The crawlers framework includes a metadata generation system for producing standardized 
XML metadata for datasets. Metadata builders convert source dataset models into 
XML formats like DataCite or OpenAIRE.

Key features:
- **Section-based architecture**: Modular sections that can be overridden
- **Protocol-based input**: Works with any dataset matching the required protocol
- **Extensible**: Subclass to customize for specific data sources
- **Standards compliant**: Built-in support for DataCite 4.5 and OpenAIRE v4.0

## Core Components

### MetadataBuilder Base Class

```python
class MetadataBuilder[DatasetT](ABC):
    """Abstract base class for metadata builders."""
    
    @abstractmethod
    def build(self, dataset: DatasetT) -> str:
        """
        Generate metadata for dataset.
        
        Returns:
            String with metadata (XML, JSON, etc.)
        """
```

Builders are used by `OnedataConverter` processor to generate metadata XML:

```python
OnedataConverter(
    metadata_builder=OpenAIREBuilder(),
)
```

## Built-in Builders

### DataCiteBuilder

Generates DataCite Kernel 4.5 compliant XML.

**Reference:** https://schema.datacite.org/meta/kernel-4.5/

**Required dataset protocol:**

```python
class DataCiteDataset(Protocol):
    identifier: str
    title: str
    datetime: str | None      # Collection date
    geometry: dict | None     # GeoJSON Polygon
    files: Sequence[DataCiteFile]
    self_link: str | None     # Related URL
```

**Configurable class attributes:**

```python
class DataCiteBuilder(MetadataBuilder[DataCiteDataset]):
    creator_name: str = "Unknown Creator"
    publisher_name: str = "Unknown Publisher"
    resource_type_general: str = "Dataset"
    resource_type_value: str = "dataset"
    default_subjects: list[str] = []
    default_description: str = ""
    default_rights: str = ""
```

**Generated sections:**

| Section | DataCite Property | Requirement |
|---------|-------------------|-------------|
| Identifier | `identifier` | Mandatory |
| Creators | `creators` | Mandatory |
| Titles | `titles` | Mandatory |
| Publisher | `publisher` | Mandatory |
| Publication Year | `publicationYear` | Mandatory |
| Resource Type | `resourceType` | Mandatory |
| Subjects | `subjects` | Recommended |
| Dates | `dates` | Recommended |
| Geo Locations | `geoLocations` | Recommended |
| Descriptions | `descriptions` | Recommended |
| Related Identifiers | `relatedIdentifiers` | Recommended |
| Rights | `rightsList` | Optional |

### OpenAIREBuilder

Generates OpenAIRE v4.0 compliant XML.

**Reference:** https://openaire-guidelines-for-literature-repository-managers.readthedocs.io/en/v4.0.0/

**Required dataset protocol:**

```python
class Dataset(Protocol):
    identifier: str
    title: str
    description: str
    publisher: str
    issued: str              # Publication date (ISO format)
    files: Sequence[DatasetFile]
    language: str            # e.g. "en", "Polish"
    keywords: list[str]
    access_level: str        # e.g. "public"
    spatial: str | None      # Bounding box: "west,south,east,north"
    temporal: str | None     # Time coverage
```

**Generated sections:**

| Section | OpenAIRE Element | Requirement |
|---------|------------------|-------------|
| Title | `datacite:titles` | Mandatory |
| Creator | `datacite:creators` | Mandatory |
| Language | `dc:language` | Mandatory if Applicable |
| Publisher | `dc:publisher` | Mandatory if Applicable |
| Publication Date | `datacite:dates` | Mandatory |
| Resource Type | `oaire:resourceType` | Mandatory |
| Description | `dc:description` | Mandatory if Applicable |
| Identifier | `datacite:identifier` | Mandatory |
| Access Rights | `datacite:rights` | Mandatory |
| Subjects | `datacite:subjects` | Mandatory if Applicable |
| Temporal Coverage | `dc:coverage` | Recommended |
| Geo Location | `datacite:geoLocations` | Optional |
| File Location | `oaire:file` | Mandatory if Applicable |

**Built-in vocabularies:**

- **COAR Access Rights**: Maps access levels to URIs
- **MIME Types**: Infers from file extensions
- **Language codes**: Normalizes to ISO 639

## Extending Builders

### Method 1: Override Class Attributes

For simple customizations, subclass and set attributes:

```python
from crawlers.core.metadata.datacite import DataCiteBuilder

class EODCDataCiteBuilder(DataCiteBuilder):
    """DataCite builder for EODC Sentinel-1 data."""
    
    creator_name = "European Space Agency"
    publisher_name = "EODC"
    resource_type_general = "Dataset"
    resource_type_value = "Earth observation data"
    
    default_subjects = [
        "Sentinel-1",
        "Synthetic Aperture Radar",
        "SAR",
        "Copernicus",
    ]
    
    default_description = (
        "Sentinel-1 Level-1 Ground Range Detected (GRD) product."
    )
    
    default_rights = "Copernicus Open Access Licence"
```

### Method 2: Override Section Builders

For more control, override specific section methods:

```python
class CustomDataCiteBuilder(DataCiteBuilder):
    """Custom DataCite builder with extended metadata."""
    
    def build_creators_section(
        self, root: ET.Element, ctx: DataCiteContext
    ) -> None:
        """Build custom creators section with affiliations."""
        creators = ET.SubElement(root, "creators")
        creator = ET.SubElement(creators, "creator")
        
        creator_name = ET.SubElement(creator, "creatorName")
        creator_name.text = ctx.dataset.publisher  # Use publisher as creator
        
        # Add affiliation
        affiliation = ET.SubElement(creator, "affiliation")
        affiliation.text = "Institute of Oceanology PAN"
    
    def build_subjects_section(
        self, root: ET.Element, ctx: DataCiteContext
    ) -> None:
        """Build subjects from dataset keywords."""
        keywords = getattr(ctx.dataset, 'keywords', [])
        if not keywords:
            return
        
        subjects = ET.SubElement(root, "subjects")
        for keyword in keywords:
            subject = ET.SubElement(subjects, "subject")
            subject.text = keyword
```

### Method 3: Modify Section List

Add, remove, or reorder sections by overriding `get_sections()`:

```python
class ExtendedDataCiteBuilder(DataCiteBuilder):
    """DataCite builder with additional custom section."""
    
    def get_sections(self):
        """Add custom section after standard ones."""
        sections = super().get_sections()
        sections.append(self.build_funding_section)
        return sections
    
    def build_funding_section(
        self, root: ET.Element, ctx: DataCiteContext
    ) -> None:
        """Build funding information section."""
        funding = ET.SubElement(root, "fundingReferences")
        ref = ET.SubElement(funding, "fundingReference")
        
        funder = ET.SubElement(ref, "funderName")
        funder.text = "European Commission"
        
        award = ET.SubElement(ref, "awardNumber")
        award.text = "H2020-123456"
```

## Creating a New Metadata Builder

### Step 1: Define Dataset Protocol

Define the interface your builder expects:

```python
from typing import Protocol, Sequence

class MyDatasetFile(Protocol):
    url: str
    size: int | None

class MyDataset(Protocol):
    identifier: str
    title: str
    description: str
    created: str
    files: Sequence[MyDatasetFile]
    tags: list[str]
```

### Step 2: Define Context Class

Context holds preprocessed data passed to section builders:

```python
from dataclasses import dataclass

@dataclass
class MyMetadataContext:
    dataset: MyDataset
    formatted_date: str
    normalized_tags: list[str]
```

### Step 3: Implement Builder

```python
from crawlers.core.abc.metadata import MetadataBuilder

class MyMetadataBuilder(MetadataBuilder[MyDataset]):
    """Custom metadata builder for MyDataset."""
    
    # Configurable defaults
    default_creator: str = "My Organization"
    schema_version: str = "1.0"
    
    def build(self, dataset: MyDataset) -> str:
        """Generate custom XML metadata."""
        ctx = self._build_context(dataset)
        
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<metadata version="{self.schema_version}">',
        ]
        
        for section_builder in self.get_sections():
            section_lines = section_builder(ctx)
            if section_lines:
                lines.extend(section_lines)
        
        lines.append('</metadata>')
        return '\n'.join(lines)
    
    def get_sections(self) -> list[Callable[[MyMetadataContext], list[str]]]:
        """Define section builders."""
        return [
            self.build_identifier_section,
            self.build_title_section,
            self.build_description_section,
            self.build_dates_section,
            self.build_files_section,
            self.build_tags_section,
        ]
    
    def _build_context(self, dataset: MyDataset) -> MyMetadataContext:
        """Preprocess dataset for section builders."""
        return MyMetadataContext(
            dataset=dataset,
            formatted_date=self._format_date(dataset.created),
            normalized_tags=[t.lower().strip() for t in dataset.tags],
        )
    
    # --- Section Builders ---
    
    def build_identifier_section(self, ctx: MyMetadataContext) -> list[str]:
        return [
            '  <identifier>',
            f'    {self._escape(ctx.dataset.identifier)}',
            '  </identifier>',
        ]
    
    def build_title_section(self, ctx: MyMetadataContext) -> list[str]:
        return [
            '  <title>',
            f'    {self._escape(ctx.dataset.title)}',
            '  </title>',
        ]
    
    def build_description_section(self, ctx: MyMetadataContext) -> list[str]:
        if not ctx.dataset.description:
            return []
        return [
            '  <description>',
            f'    {self._escape(ctx.dataset.description)}',
            '  </description>',
        ]
    
    def build_dates_section(self, ctx: MyMetadataContext) -> list[str]:
        return [
            '  <dates>',
            f'    <created>{ctx.formatted_date}</created>',
            '  </dates>',
        ]
    
    def build_files_section(self, ctx: MyMetadataContext) -> list[str]:
        if not ctx.dataset.files:
            return []
        
        lines = ['  <files>']
        for f in ctx.dataset.files:
            size_attr = f' size="{f.size}"' if f.size else ''
            lines.append(f'    <file{size_attr}>{self._escape(f.url)}</file>')
        lines.append('  </files>')
        return lines
    
    def build_tags_section(self, ctx: MyMetadataContext) -> list[str]:
        if not ctx.normalized_tags:
            return []
        
        lines = ['  <tags>']
        for tag in ctx.normalized_tags:
            lines.append(f'    <tag>{self._escape(tag)}</tag>')
        lines.append('  </tags>')
        return lines
    
    # --- Helpers ---
    
    def _escape(self, text: str) -> str:
        """Escape XML special characters."""
        return (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
        )
    
    def _format_date(self, date_str: str) -> str:
        """Format date to ISO standard."""
        # Implementation depends on input format
        return date_str[:10]  # Simple truncation to YYYY-MM-DD
```

### Step 4: Use in Converter

```python
from crawlers.core.processors.converters import OnedataConverter

OnedataConverter(
    metadata_builder=MyMetadataBuilder(),
)
```

## Architecture Pattern

```
┌──────────────────────────────────────────────────────────────┐
│                      MetadataBuilder                         │
├──────────────────────────────────────────────────────────────┤
│  build(dataset) ─────────────────────────────────────────┐   │
│                                                          │   │
│  ┌────────────────┐                                      │   │
│  │ _build_context │  Dataset → Context                   │   │
│  └────────────────┘                                      │   │
│           │                                              │   │
│           ▼                                              │   │
│  ┌────────────────┐                                      │   │
│  │  get_sections  │  Returns list of section builders    │   │
│  └────────────────┘                                      │   │
│           │                                              │   │
│           ▼                                              │   │
│  ┌─────────────────────────────────────────────────┐     │   │
│  │  Section Builders (called in order)             │     │   │
│  │  ┌──────────────┐ ┌──────────────┐              │     │   │
│  │  │ build_title  │ │ build_dates  │ ...          │     │   │
│  │  └──────────────┘ └──────────────┘              │     │   │
│  └─────────────────────────────────────────────────┘     │   │
│           │                                              │   │
│           ▼                                              │   │
│  ┌────────────────┐                                      │   │
│  │ Combine & XML  │  → XML String                        │   │
│  └────────────────┘                                      │   │
└──────────────────────────────────────────────────────────────┘
```

## Best Practices

### Protocol Design

Define minimal required attributes:

```python
class Dataset(Protocol):
    # Only what's truly needed
    identifier: str
    title: str
    files: Sequence[DatasetFile]
```

Use optional attributes with defaults:

```python
def build_description_section(self, ctx: Context) -> list[str]:
    description = getattr(ctx.dataset, 'description', '')
    if not description:
        return []  # Skip section if not available
    ...
```

### XML Escaping

Always escape user content:

```python
def _escape(self, text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
    )
```

### Conditional Sections

Return empty list to skip sections:

```python
def build_geo_section(self, ctx: Context) -> list[str]:
    if not ctx.dataset.geometry:
        return []  # Section omitted from output
    ...
```

### Vocabulary Mapping

Use dictionaries for controlled vocabularies:

```python
ACCESS_RIGHTS_MAP = {
    "public": ("http://purl.org/coar/access_right/c_abf2", "open access"),
    "restricted": ("http://purl.org/coar/access_right/c_16ec", "restricted access"),
}

def _get_access_rights(self, level: str) -> tuple[str, str]:
    return ACCESS_RIGHTS_MAP.get(level, ACCESS_RIGHTS_MAP["public"])
```

### Context Preprocessing

Do heavy processing once in context:

```python
def _build_context(self, dataset: Dataset) -> Context:
    return Context(
        dataset=dataset,
        # Pre-compute expensive operations
        normalized_keywords=[k.lower() for k in dataset.keywords],
        parsed_date=self._parse_date(dataset.issued),
        file_count=len(dataset.files),
    )
```

## Complete Example: Plugin-specific Builder

```python
# plugins/myplugin/metadata.py

from crawlers.core.metadata.openaire import OpenAIREBuilder, OpenAIREContext

class MyPluginOpenAIREBuilder(OpenAIREBuilder):
    """
    OpenAIRE builder customized for MyPlugin data source.
    
    Adds:
    - Custom creator from dataset.organization field
    - Additional funding reference section
    """
    
    def build_creator_section(self, ctx: OpenAIREContext) -> list[str]:
        """Override to use organization from dataset."""
        org = getattr(ctx.dataset, 'organization', ctx.dataset.publisher)
        return [
            "  <!-- 2. Creator (M) -->",
            "  <datacite:creators>",
            "    <datacite:creator>",
            '      <datacite:creatorName nameType="Organizational">',
            f"        {self._escape_xml(org)}",
            "      </datacite:creatorName>",
            "    </datacite:creator>",
            "  </datacite:creators>",
        ]
    
    def get_sections(self):
        """Add funding section."""
        sections = super().get_sections()
        # Insert before files section
        files_idx = next(
            i for i, s in enumerate(sections) 
            if s.__name__ == 'build_files_section'
        )
        sections.insert(files_idx, self.build_funding_section)
        return sections
    
    def build_funding_section(self, ctx: OpenAIREContext) -> list[str]:
        """Add funding reference if available."""
        funding = getattr(ctx.dataset, 'funding', None)
        if not funding:
            return []
        
        return [
            "  <!-- 19. Funding Reference (R) -->",
            "  <oaire:fundingReferences>",
            "    <oaire:fundingReference>",
            f"      <oaire:funderName>{self._escape_xml(funding)}</oaire:funderName>",
            "    </oaire:fundingReference>",
            "  </oaire:fundingReferences>",
        ]
```

**Usage:**

```python
# plugins/myplugin/crawler.py

from crawlers.plugins.myplugin.metadata import MyPluginOpenAIREBuilder

def build_pipeline(self, client: ApiClient) -> ProcessorPipeline:
    return ProcessorPipeline([
        ...
        OnedataConverter(
            metadata_builder=MyPluginOpenAIREBuilder(),
        ),
        ...
    ])
```
