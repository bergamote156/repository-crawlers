"""
eCUDO API Client

Low-level HTTP client and iterators for eCUDO.pl API.
"""

from ecudo.ecudo_api.client import EcudoClient
from ecudo.ecudo_api.iterator import EcudoDatasetIDIterator

__all__ = ["EcudoClient", "EcudoDatasetIDIterator"]
