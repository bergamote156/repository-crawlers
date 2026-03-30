"""Metadata Generator Base."""

# pylint: disable=too-few-public-methods

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from abc import ABC, abstractmethod


class MetadataBuilder[DatasetT](ABC):
    """Abstract base class for metadata builders."""

    @abstractmethod
    def build(self, dataset: DatasetT) -> str:
        """
        Generate metadata for dataset.

        Args:
            dataset: Dataset to process (InputDataset or derived)

        Returns:
            String with metadata (XML, JSON, etc.)
        """
        raise NotImplementedError
