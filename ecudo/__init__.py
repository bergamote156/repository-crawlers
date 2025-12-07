"""
eCUDO Crawler

A modular crawler for discovering and processing public scientific datasets
from eCUDO.pl for registration in Onedata.

Architecture Overview
---------------------
The crawler is organized into several modules with clear responsibilities:

- **crawler/**: HTTP client and ID iterators for eCUDO API
- **models/**: Data structures (EcudoRecord, FileInfo, OnedataDataset)
- **parsers/**: JSON-LD to model conversion
- **serializers/**: Model to metadata format conversion (OpenAIRE, etc.)
- **processors/**: Pipeline processors (fetching, validation, filtering, writing)
- **orchestration/**: Parallel processing infrastructure

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

# Re-export main components for convenience
from ecudo.crawler import EcudoClient, RecordIDIterator
from ecudo.models import EcudoRecord, FileInfo, OnedataDataset, OnedataFile
from ecudo.orchestration import ParallelFetcher, ProcessingStats
from ecudo.parsers import EcudoParser
from ecudo.processors import (
    DiversityFilter,
    MetadataFetcher,
    OnedataConverter,
    Processor,
    ProcessorPipeline,
    URLValidator,
)
from ecudo.serializers import MetadataSerializer, OpenAIRESerializer

__all__ = [
    # Version
    "__version__",
    # Crawler
    "EcudoClient",
    "RecordIDIterator",
    # Models
    "EcudoRecord",
    "FileInfo",
    "OnedataDataset",
    "OnedataFile",
    # Parsers
    "EcudoParser",
    # Serializers
    "MetadataSerializer",
    "OpenAIRESerializer",
    # Processors
    "Processor",
    "ProcessorPipeline",
    "MetadataFetcher",
    "URLValidator",
    "DiversityFilter",
    "OnedataConverter",
    # Orchestration
    "ParallelFetcher",
    "ProcessingStats",
]
