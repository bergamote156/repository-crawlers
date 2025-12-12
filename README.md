# Public Data Crawlers

This repository contains crawlers for automatic discovery and registration 
of public scientific datasets in the [Onedata](https://onedata.org/) system.

## About

The goal of this project is to create tools that enable:
- Crawling public scientific data repositories
- Extracting metadata from available datasets
- Automatic registration of datasets in the Onedata ecosystem

## Components

| Component | Description | Status |
|-----------|-------------|--------|
| [eCUDO Crawler](ecudo/) | Crawler for Polish university datasets | ✅ Available |
| [Dataset Registrar](registrar/) | Register crawled datasets in Onedata | ✅ Available |

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### eCUDO Crawler

The eCUDO crawler discovers datasets from Polish scientific institutions.

```bash
# List available organizations
python -m ecudo list-orgs

# Crawl datasets from an organization
python -m ecudo crawl iopan

# Crawl with options
python -m ecudo crawl iopan --max-records 100 --output-dir ./data

# Disable URL validation (faster)
python -m ecudo crawl mir --no-url-validation

# Convert JSONL output to JSON
python -m ecudo convert data/iopan_processed.jsonl

# Show current configuration
python -m ecudo show-config
```

### Dataset Registrar

The registrar takes crawled datasets and registers them in Onedata.

```bash
# Register datasets from JSON file
python -m registrar register datasets.json

# Register with limit (useful for testing)
python -m registrar register datasets.json --limit 10

# Dry run (validate without registering)
python -m registrar register datasets.json --dry-run

# List HTTP readonly spaces on provider
python -m registrar list-spaces

# List HTTP readonly storages on provider
python -m registrar list-storages

# Show current configuration
python -m registrar show-config
```

#### Required Environment Variables

```bash
export REGISTRAR_ADMIN_TOKEN="your-onepanel-admin-token"
export REGISTRAR_SPACE_OWNER_TOKEN="your-onezone-user-token"
export REGISTRAR_ONEZONE_DOMAIN="demo.onedata.org"
export REGISTRAR_ONEPROVIDER_DOMAIN="provider.demo.onedata.org"

# Optional: for DOI handle registration
export REGISTRAR_HANDLE_SERVICE_ID="your-handle-service-id"
```

### Configuration

Both tools support hierarchical configuration (in order of priority):
1. CLI arguments
2. Config file (YAML)
3. Environment variables

See configuration examples:
- `ecudo/config.example.yaml` - eCUDO crawler options
- `registrar/config.example.yaml` - Dataset registrar options

## Architecture

- [eCUDO Architecture](ecudo/docs/ARCHITECTURE.md)
- [Registrar Architecture](registrar/docs/ARCHITECTURE.md)

## License

MIT
