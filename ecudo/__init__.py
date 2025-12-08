"""
eCUDO Crawler

A modular crawler for discovering and processing public scientific datasets
from eCUDO.pl for registration in Onedata.

Architecture Overview
---------------------
The crawler is organized into several modules with clear responsibilities:

- **ecudo_api/**: Low-level HTTP client and ID iterators for eCUDO API
- **models/**: Data structures (EcudoRecord, FileInfo, OnedataDataset)
- **parsers/**: JSON-LD to model conversion
- **metadata/**: Metadata format generators (OpenAIRE, etc.)
- **processors/**: Pipeline processors (fetching, validation, filtering, writing)
- **orchestration/**: Parallel processing infrastructure
- **crawler.py**: High-level crawl orchestration (EcudoCrawler)

See ARCHITECTURE.md for detailed documentation.

Quick Start
-----------
    # List organizations
    python -m ecudo list-orgs

    # Crawl an organization
    python -m ecudo crawl iopan --max-records 100

    # Convert output
    python -m ecudo convert data/iopan_processed.jsonl
"""

__version__ = "0.3.0"
