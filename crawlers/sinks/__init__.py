"""
Concrete sink implementations.

See crawlers.core0.sink for the Sink abstract base class.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from crawlers.sinks.jsonl import JSONLSink
from crawlers.sinks.null_sink import NullSink

__all__ = ["JSONLSink", "NullSink"]
