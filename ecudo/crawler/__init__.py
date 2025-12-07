"""
eCUDO Crawler

HTTP client and iterators for crawling eCUDO.pl API.
"""

from ecudo.crawler.client import EcudoClient
from ecudo.crawler.iterator import RecordIDIterator

__all__ = ["EcudoClient", "RecordIDIterator"]
