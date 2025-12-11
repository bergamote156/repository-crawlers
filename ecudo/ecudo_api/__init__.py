"""
eCUDO API Client

Low-level HTTP client and iterators for eCUDO.pl API.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from ecudo.ecudo_api.client import EcudoClient
from ecudo.ecudo_api.iterator import EcudoDatasetIDIterator

__all__ = ["EcudoClient", "EcudoDatasetIDIterator"]
