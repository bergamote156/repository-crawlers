"""Onedata dataset contract — shared between crawlers and registrar."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from onedata_dataset.dataset import OnedataDataset, OnedataFile

__all__ = ["OnedataDataset", "OnedataFile"]
