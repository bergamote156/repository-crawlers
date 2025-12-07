"""
eCUDO Data Models

Data structures representing eCUDO datasets and Onedata output.
"""

from ecudo.models.onedata import OnedataDataset, OnedataFile
from ecudo.models.record import EcudoRecord, FileInfo

__all__ = [
    "EcudoRecord",
    "FileInfo",
    "OnedataDataset",
    "OnedataFile",
]
