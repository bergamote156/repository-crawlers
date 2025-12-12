# Dataset Registrar Architecture

This document describes the modular architecture of the Dataset Registrar.

## Overview

The Dataset Registrar automates registration of datasets from external open science
services into Onedata. It creates HTTP storages and spaces as needed, registers files,
creates public shares, and optionally registers DOI handles.

## Module Structure

```
registrar/
├── __init__.py           # Package exports and version
├── __main__.py           # CLI entry point (python -m registrar)
├── cli.py                # Command-line interface (click)
├── config.py             # Configuration management
├── output.py             # Logging utilities
│
├── docs/
│   └── ARCHITECTURE.md   # This file
│
├── api/                  # Onedata API clients
│   ├── __init__.py       # Client exports
│   ├── onepanel.py       # OnepanelClient - admin operations (storages, space support)
│   ├── onezone.py        # OnezoneClient - space creation, tokens, handles
│   └── oneprovider.py    # OneproviderClient - file registration, shares
│
├── models.py             # Data structures (InputDataset, RegistrationResult)
├── cache.py              # ResourceCache - spaces/storages cache
├── operations.py         # Business logic functions
└── registrar.py          # DatasetRegistrar - high-level orchestration
```

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           Registration Flow                                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   ┌───────────────────┐                                                         │
│   │   datasets.json   │  Input: list of datasets with files and metadata        │
│   │   (input file)    │                                                         │
│   └────────┬──────────┘                                                         │
│            │                                                                    │
│            ▼                                                                    │
│   ┌───────────────────┐                                                         │
│   │ DatasetRegistrar  │  Orchestrator: loads config, initializes clients        │
│   │   .run()          │                                                         │
│   └────────┬──────────┘                                                         │
│            │                                                                    │
│            ▼                                                                    │
│   ┌───────────────────┐                                                         │
│   │   load_cache()    │  Pre-load HTTP readonly spaces/storages                 │
│   │   (operations.py) │                                                         │
│   └────────┬──────────┘                                                         │
│            │                                                                    │
│            ▼                                                                    │
│   ┌──────────────────────────────────────────────────────────────────────────┐  │
│   │                    For each dataset:                                     │  │
│   │                                                                          │  │
│   │   ┌────────────────────────┐                                             │  │
│   │   │ ensure_space_and_      │  Extract domain from file URLs              │  │
│   │   │ storage()              │  Create storage + space if not cached       │  │
│   │   └───────────┬────────────┘                                             │  │
│   │               │ (space_id, storage_id)                                   │  │
│   │               ▼                                                          │  │
│   │   ┌────────────────────────┐                                             │  │
│   │   │ register_dataset_      │  Register each file in Onedata              │  │
│   │   │ files()                │  Skip if file already exists                │  │
│   │   └───────────┬────────────┘                                             │  │
│   │               │ (registered_count, skipped_count)                        │  │
│   │               ▼                                                          │  │
│   │   ┌────────────────────────┐                                             │  │
│   │   │ find_or_create_        │  Create public share for dataset directory  │  │
│   │   │ share()                │  Reuse existing share if matches            │  │
│   │   └───────────┬────────────┘                                             │  │
│   │               │ (share_id)                                               │  │
│   │               ▼                                                          │  │
│   │   ┌────────────────────────┐                                             │  │
│   │   │ find_or_register_      │  Register DOI handle (optional)             │  │
│   │   │ handle()               │  Requires handle_service_id configured      │  │
│   │   └────────────────────────┘                                             │  │
│   │                                                                          │  │
│   └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Key Components

### API Clients (`api/`)

Classes that encapsulate Onedata REST API calls. Each client holds configuration
(domain, token) and a requests session.

**OnepanelClient** (`api/onepanel.py`)
- Admin operations on Oneprovider
- Storage management: `list_storages()`, `add_storage()`, `get_storage_details()`
- Space support: `list_spaces()`, `support_space()`, `get_space_details()`

**OnezoneClient** (`api/onezone.py`)
- User operations on Onezone
- Space creation: `create_space()`, `create_support_token()`
- Handle registration: `register_handle()`

**OneproviderClient** (`api/oneprovider.py`)
- Data operations on Oneprovider
- File registration: `register_file()`, `lookup_file_id()`, `get_file_attrs()`
- Shares: `create_share()`, `get_share_details()`

### ResourceCache (`cache.py`)

Caches spaces and storages to minimize API calls. Only tracks HTTP readonly
storages with matching space names (convention used for dataset registration).

```python
cache = ResourceCache()
cache.add_space(name="example.com", space_id="abc123", storage_id="def456")
cached = cache.get_space_by_name("example.com")
```

### Operations (`operations.py`)

Pure functions implementing business logic. Dependencies passed explicitly.

| Function | Description |
|----------|-------------|
| `load_cache()` | Pre-load spaces/storages into cache |
| `ensure_space_and_storage()` | Create space+storage if not cached |
| `register_dataset_files()` | Register all files for a dataset |
| `find_or_create_share()` | Find existing or create new share |
| `find_or_register_handle()` | Find existing or register new DOI handle |

### DatasetRegistrar (`registrar.py`)

High-level orchestrator that ties everything together:

```python
registrar = DatasetRegistrar(config)
summary = registrar.run(datasets_file="datasets.json", limit=10)
```

## Configuration

Configuration uses a three-layer hierarchy (higher overrides lower):
1. Environment variables (`REGISTRAR_*` prefix)
2. Config file (`registrar.yaml`)
3. CLI arguments

### Config Sections

| Section | Description |
|---------|-------------|
| `onedata` | Onezone/Oneprovider domains, ports |
| `tokens` | Authentication tokens (admin, space owner, handle service) |
| `storage` | Default storage size |
| `output` | Output directory, log file |
| `logging` | Log level |

See `config.example.yaml` for all available options.

## CLI Commands

```bash
# Register datasets from JSON file
python -m registrar register datasets.json

# Register with options
python -m registrar register datasets.json --limit 10 --dry-run

# List HTTP readonly spaces
python -m registrar list-spaces

# List HTTP readonly storages
python -m registrar list-storages

# Show current configuration
python -m registrar show-config
```

## Design Decisions

### Classes vs Functions

- **Classes** are used where state is maintained:
  - API clients (session, config)
  - ResourceCache (cached data)
  - DatasetRegistrar (holds dependencies)

- **Functions** are used for stateless business logic:
  - All operations in `operations.py`
  - Pure transformations with explicit dependencies

### Naming Conventions

- `registrar/` - module name (consistent with "Dataset Registrar")
- `operations.py` - business logic functions (pythonic alternative to "services")
- `api/` - REST API clients (clear purpose)

### Error Handling

- API clients raise exceptions on HTTP errors
- Operations catch and log errors, continue processing other datasets
- Summary reports successful/failed counts
