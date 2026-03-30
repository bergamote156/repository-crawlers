# ECUDO Record Structure and OpenAIRE Mapping

This document describes the structure of JSON-LD records from ECUDO and their
mapping to OpenAIRE Guidelines for Literature Repository Managers v4.0.0.

## ECUDO JSON-LD Record Structure

Records from ECUDO follow the
[Project Open Data](https://project-open-data.cio.gov/v1.1/schema/) JSON-LD
schema (DCAT-based).

### Root Level Fields

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `@context` | string | Yes | JSON-LD context URL | `"https://project-open-data.cio.gov/v1.1/schema/catalog.jsonld"` |
| `@type` | string | Yes | Record type, always `"dcat:Dataset"` | `"dcat:Dataset"` |
| `identifier` | string | Yes | Unique identifier in URN format | `"urn:SDN:CDI:iopan.pl:uuid:0cd81dda-1260-40b0-b917-1e2419e93d76"` |
| `title` | string | Yes | Dataset title | `"r/v Oceania, VDR Data"` |
| `description` | string | Yes | Dataset description | `"Environmental data from moving ship"` |
| `issued` | string | Yes | Publication date (ISO 8601) | `"2022-10-08"` |
| `modified` | string | Yes | Last modification date (ISO 8601) | `"2022-10-08"` |
| `language` | string | Yes | Language name (not code!) | `"English"` |
| `accessLevel` | string | Yes | Access level | `"public"` |
| `keywords` | array[string] | Yes | Subject keywords | `["Oceanographic geographical features", "research vessel"]` |
| `spatial` | string | No | Bounding box coordinates | `"19.371174,77.327103,19.413743999999998,77.327149"` |
| `temporal` | string | No | Temporal coverage (ISO 8601 interval) | `"2013-08-13T15:49:59/2013-08-13T15:54:59"` |
| `publisher` | object | Yes | Publisher organization | See below |
| `contactPoint` | object | Yes | Contact information | See below |
| `distribution` | array[object] | Yes | File distributions | See below |

### Publisher Object

| Field | Type | Expected Value | Notes |
|-------|------|----------------|-------|
| `@context` | string | `"https://project-open-data.cio.gov/v1.1/schema/catalog.jsonld"` | |
| `@type` | string | `"org:Organization"` | Log warning if different |
| `name` | string | Organization name | `"Institute of Oceanology, Polish Academy of Sciences"` |

### ContactPoint Object

| Field | Type | Expected Value | Notes |
|-------|------|----------------|-------|
| `@context` | string | `"https://project-open-data.cio.gov/v1.1/schema/catalog.jsonld"` | |
| `@type` | string | `"vCard:contact"` | Log warning if different |
| `fn` | string | Contact name | `"Institute of Oceanology, Polish Academy of Sciences"` |
| `hasEmail` | string | Contact email | `"data_manager@iopan.pl"` |

### Distribution Object

| Field | Type | Expected Value | Notes |
|-------|------|----------------|-------|
| `@context` | string | `"https://project-open-data.cio.gov/v1.1/schema/catalog.jsonld"` | |
| `@type` | string | `"dcat:Distribution"` | Log warning if different |
| `downloadURL` | string | File download URL | Required |
| `format` | string | Format identifier | e.g., `"WWW:DOWNLOAD-1.0-http--download"` |

## Known Field Values

These are the values observed in production data. The parser logs warnings when
unexpected values appear.

### @type Values

| Context | Expected Value |
|---------|----------------|
| Root record | `"dcat:Dataset"` |
| Distribution | `"dcat:Distribution"` |
| Publisher | `"org:Organization"` |
| ContactPoint | `"vCard:contact"` |

### accessLevel Values

| Value | COAR Access Right | URI |
|-------|-------------------|-----|
| `"public"` | open access | `http://purl.org/coar/access_right/c_abf2` |

### Identifier Format

IOPAN identifiers follow the pattern:
```
urn:SDN:CDI:<namespace>:uuid:<uuid>
```

Example: `urn:SDN:CDI:iopan.pl:uuid:0cd81dda-1260-40b0-b917-1e2419e93d76`

This is a valid URN and should use `identifierType="URN"` in OpenAIRE metadata.

### Spatial Format

Bounding box as comma-separated coordinates:
```
<westLon>,<southLat>,<eastLon>,<northLat>
```

Example: `"19.371174,77.327103,19.413743999999998,77.327149"`

### Temporal Format

ISO 8601 interval format:
```
<startDateTime>/<endDateTime>
```

Example: `"2013-08-13T15:49:59/2013-08-13T15:54:59"`

## OpenAIRE Mapping

Mapping from ECUDO fields to OpenAIRE Guidelines v4.0.0 elements.

### Mandatory Fields (M)

| OpenAIRE Element | ECUDO Source | Notes |
|------------------|--------------|-------|
| `datacite:title` | `title` | Add `xml:lang` from normalized language |
| `datacite:creator` | `publisher.name` | Use as organizational creator (`nameType="Organizational"`) |
| `datacite:date` (Issued) | `issued` | `dateType="Issued"` |
| `oaire:resourceType` | hardcoded | `"dataset"` with COAR URI `c_ddb1` |
| `datacite:identifier` | `identifier` | `identifierType="URN"` |
| `datacite:rights` | `accessLevel` | Map to COAR vocabulary |

### Mandatory if Applicable (MA)

| OpenAIRE Element | ECUDO Source | Notes |
|------------------|--------------|-------|
| `dc:language` | `language` | Normalize to ISO 639-1 code |
| `dc:publisher` | `publisher.name` | |
| `dc:description` | `description` | Add `xml:lang` |
| `datacite:subject` | `keywords[]` | One element per keyword |
| `oaire:file` | `distribution[].downloadURL` | Add `accessRightsURI` and `mimeType` |

### Recommended/Optional Fields

| OpenAIRE Element | ECUDO Source | Notes |
|------------------|--------------|-------|
| `dc:coverage` | `temporal` | Temporal coverage |
| `datacite:geoLocation` | `spatial` | Parse bounding box |

### Not Currently Mapped

| OpenAIRE Element | Potential Source | Status |
|------------------|------------------|--------|
| `datacite:contributor` | N/A              | Not available in ECUDO |
| `oaire:fundingReference` | N/A              | Not available in ECUDO |
| `datacite:alternateIdentifier` | N/A              | Not available |
| `datacite:relatedIdentifier` | N/A              | Not available |

## Validation Rules

The parser validates and logs warnings for:

1. **Unexpected @type values** - Any @type that doesn't match expected values
2. **Unknown accessLevel** - Values other than "public", "restricted", "non-public"
3. **Unknown root fields** - New fields not in the known schema
4. **Missing required fields** - Records without identifier or distribution

## Change Log

- **2024-12-10**: Initial documentation based on IOPAN sample records
