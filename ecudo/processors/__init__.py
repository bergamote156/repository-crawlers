"""
eCUDO Processors

Pipeline processors for fetching, filtering, validating, converting,
and writing dataset records.
"""

from ecudo.processors.base import Processor
from ecudo.processors.converters import OnedataConverter
from ecudo.processors.fetchers import MetadataFetcher
from ecudo.processors.filters import DiversityFilter
from ecudo.processors.pipeline import ProcessorPipeline
from ecudo.processors.validators import URLValidator
from ecudo.processors.writers import JSONLWriter

__all__ = [
    # Base
    "Processor",
    # Pipeline
    "ProcessorPipeline",
    # Fetchers
    "MetadataFetcher",
    # Validators
    "URLValidator",
    # Filters
    "DiversityFilter",
    # Converters
    "OnedataConverter",
    # Writers
    "JSONLWriter",
]
