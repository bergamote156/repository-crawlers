"""
eCUDO Data Models

Data structures representing eCUDO datasets and Onedata output.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from ecudo.models.ecudo import EcudoDataset, EcudoFile
from ecudo.models.onedata import OnedataDataset, OnedataFile

__all__ = [
    "EcudoDataset",
    "EcudoFile",
    "OnedataDataset",
    "OnedataFile",
]
