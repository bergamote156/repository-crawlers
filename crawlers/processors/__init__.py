"""
Built-in pipeline processors.

See crawlers.core.abc.processor for the Processor abstract base class.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from crawlers.processors.converters import OnedataConverter
from crawlers.processors.filters import DiversityFilter
from crawlers.processors.parsers import Parser, ParserProcessor
from crawlers.processors.pipeline import ProcessorPipeline
from crawlers.processors.resolvers import DatasetResolver
from crawlers.processors.tap import Tap
from crawlers.processors.validators import URLValidator

__all__ = [
    "DatasetResolver",
    "DiversityFilter",
    "OnedataConverter",
    "Parser",
    "ParserProcessor",
    "ProcessorPipeline",
    "Tap",
    "URLValidator",
]
