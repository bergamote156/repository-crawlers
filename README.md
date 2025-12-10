# Public Data Crawlers

This repository contains crawlers for automatic discovery and registration 
of public scientific datasets in the [Onedata](https://onedata.org/) system.

## About

The goal of this project is to create tools that enable:
- Crawling public scientific data repositories
- Extracting metadata from available datasets
- Automatic registration of datasets in the Onedata ecosystem

## Supported Data Sources

| Source | Description | Status |
|--------|-------------|--------|
| [eCUDO](http://central.ecudo.pl/) | Aggregator of datasets from Polish universities | ✅ Available |

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

### Configuration

Configuration can be set via (in order of priority):
1. CLI arguments
2. Config file (`ecudo.yaml`)
3. Environment variables (`ECUDO_*` prefix)

See `ecudo/config.example.yaml` for all available options.

## Architecture

See [ARCHITECTURE.md](ecudo/docs/ARCHITECTURE.md) for detailed documentation.

## License

MIT
