"""
eCUDO Processors

Pipeline processors for fetching, filtering, validating, converting,
and writing dataset records.

Creating a Custom Processor
---------------------------
To create a new processor, subclass Processor[I, O] and implement process():

    from ecudo.processors import Processor
    from ecudo.models.ecudo import EcudoDataset

    class MyFilter(Processor[EcudoDataset, EcudoDataset]):
        def __init__(self, threshold: float):
            self.threshold = threshold
            self._filtered = 0

        async def process(self, record: EcudoDataset) -> EcudoDataset | None:
            if self.should_skip(record):
                self._filtered += 1
                return None  # Filter out
            return record  # Pass through

Then add your processor to the pipeline in crawler.py.

See docs/ARCHITECTURE.md for the full data flow diagram.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from ecudo.processors.base import Processor
from ecudo.processors.converters import OnedataConverter
from ecudo.processors.fetchers import DatasetFetcher
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
    "DatasetFetcher",
    # Validators
    "URLValidator",
    # Filters
    "DiversityFilter",
    # Converters
    "OnedataConverter",
    # Writers
    "JSONLWriter",
]
