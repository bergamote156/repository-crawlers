---
title: Metadata Generation
topic: crawlers/arch/metadata
generated: 2026-04-01
last_reviewed: 2026-04-01
source_modules:
  - crawlers/core/metadata.py
  - crawlers/metadata/datacite.py
  - crawlers/metadata/openaire.py
  - crawlers/plugins/eodc/metadata.py
source_commits:
  public-data-crawlers: d8a4e8e
status: draft
---

# Metadata Generation

Metadata builders produce standards-compliant XML from parsed dataset
models. The framework provides two builders — DataCite Kernel 4.5
and OpenAIRE v4.0 — both designed for extensibility via overridable
section methods.

> For how metadata builders are wired into the pipeline, see
> [Processing — OnedataConverter](processing.md#onedataconverter).
> For practical usage in plugins, see
> [Writing Plugins](../guides/writing-plugins.md).

## MetadataBuilder Abstraction

The base interface is minimal — a single generic abstract class in
`crawlers/core/metadata.py`:

```python
class MetadataBuilder[DatasetT](ABC):
    @abstractmethod
    def build(self, dataset: DatasetT) -> str: ...
```

The `OnedataConverter` processor calls `build()` for every dataset
that reaches the conversion stage, embedding the resulting XML
string into the `OnedataDataset` record.

## Template Method Pattern

Both concrete builders follow the same pattern:

1. `build(dataset)` creates a context object from the dataset.
2. `get_sections()` returns an ordered list of section builder
   methods.
3. Each section builder receives the context and produces its output
   (XML elements or string lines).
4. The results are assembled into the final XML document.

This design allows plugins to customize metadata in three ways:

- **Override a section method** — change how a specific section is
  built (e.g. custom creator name, different subject terms).
- **Override `get_sections()`** — reorder, add, or remove entire
  sections.
- **Override class-level defaults** — change values like
  `creator_name` or `publisher_name` without touching any methods.

## DataCiteBuilder

Generates XML compliant with
[DataCite Metadata Schema 4.5](https://schema.datacite.org/meta/kernel-4.5/).
Uses `xml.etree.ElementTree` for structured XML construction.

### Dataset protocol

`DataCiteDataset` requires: `identifier`, `title`, `datetime`,
`geometry`, `files`, `self_link`. The protocol uses structural
typing — any dataclass with these attributes works.

### Sections

Mandatory (M) and recommended (R) per the DataCite schema:

| Section | Status | Method |
|---------|--------|--------|
| Identifier | M | `build_identifier_section` |
| Creators | M | `build_creators_section` |
| Titles | M | `build_titles_section` |
| Publisher | M | `build_publisher_section` |
| PublicationYear | M | `build_publication_year_section` |
| ResourceType | M | `build_resource_type_section` |
| Subjects | R | `build_subjects_section` |
| Dates | R | `build_dates_section` |
| GeoLocations | R | `build_geo_locations_section` |
| Descriptions | R | `build_descriptions_section` |
| RelatedIdentifiers | R | `build_related_identifiers_section` |
| Rights | R | `build_rights_section` |

### Class-level defaults

Subclasses customize the builder by overriding these attributes:

| Attribute | Default | Purpose |
|-----------|---------|---------|
| `creator_name` | `"Unknown Creator"` | Name used in Creators |
| `publisher_name` | `"Unknown Publisher"` | Name used in Publisher |
| `resource_type_general` | `"Dataset"` | DataCite resourceTypeGeneral |
| `resource_type_value` | `"dataset"` | DataCite resourceType value |
| `default_subjects` | `[]` | Subject keywords |
| `default_description` | `""` | Fallback description |
| `default_rights` | `""` | Rights statement |

For example, `EODCDataCiteBuilder` overrides these with
Sentinel-1/Copernicus-specific values (creator: ESA, publisher:
EODC, subjects: Sentinel-1, SAR, GRD, Copernicus).

## OpenAIREBuilder

Generates XML compliant with
[OpenAIRE Guidelines v4.0](https://openaire-guidelines-for-literature-repository-managers.readthedocs.io/en/v4.0.0/).
Uses string concatenation rather than ElementTree, building XML
lines directly.

### Dataset protocol

`Dataset` requires a richer set of attributes than DataCite:
`identifier`, `title`, `description`, `publisher`, `issued`,
`files`, `language`, `keywords`, `access_level`, `spatial`,
`temporal`.

### Sections

| Section | Status | Method |
|---------|--------|--------|
| Title | M | `build_title_section` |
| Creator | M | `build_creator_section` |
| Language | MA | `build_language_section` |
| Publisher | MA | `build_publisher_section` |
| Publication Date | M | `build_publication_date_section` |
| Resource Type | M | `build_resource_type_section` |
| Description | MA | `build_description_section` |
| Identifier | M | `build_identifier_section` |
| Access Rights | M | `build_access_rights_section` |
| Subjects | MA | `build_subjects_section` |
| Temporal | R | `build_temporal_section` |
| Geo Location | R | `build_geo_location_section` |
| Files | MA | `build_files_section` |

(M = Mandatory, MA = Mandatory if Applicable, R = Recommended)

### COAR vocabulary mapping

Access rights are mapped to COAR URIs. Currently only `"public"` is
mapped (to `http://purl.org/coar/access_right/c_abf2`, "open
access"). Resource types use COAR resource type vocabulary.

### MIME type inference

The file section infers MIME types from file extensions using a
built-in mapping (`.zip`, `.csv`, `.nc`, `.tiff`, `.geojson`, etc.).
Unknown extensions fall back to no MIME type attribute.

### GeoJSON conversion

When `spatial` data is available, the geo location section extracts
bounding boxes from GeoJSON geometry. Polygon coordinates are
converted to `westBoundLongitude`, `eastBoundLongitude`,
`southBoundLatitude`, `northBoundLatitude` bounds.

## Extending Metadata Builders

The recommended approach for custom metadata is to subclass the
appropriate builder and override what you need:

```python
class MyDataCiteBuilder(DataCiteBuilder["MyDataset"]):
    creator_name = "My Organization"
    publisher_name = "My Publisher"
    default_subjects = ["Earth Science", "Remote Sensing"]

    def build_descriptions_section(self, root, ctx):
        # Custom description logic
        ...
```

For adding entirely new sections, override `get_sections()` and
append your builder method to the list:

```python
def get_sections(self):
    sections = super().get_sections()
    sections.append(self.build_custom_section)
    return sections
```

## Related Documentation

- **[Architecture Overview](_overview.md)** — system layers
- **[Processing](processing.md#onedataconverter)** — how
  OnedataConverter uses metadata builders
- **[Plugin System](plugin-system.md#defaultcrawlspec)** — where
  metadata builders are specified
- **[Writing Plugins](../guides/writing-plugins.md)** — practical
  examples
- **[Glossary](glossary.md#metadatabuilder)** — quick definition
