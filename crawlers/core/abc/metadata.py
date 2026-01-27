"""Metadata Generator Base."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from abc import ABC, abstractmethod


class MetadataBuilder[T](ABC):
    """
    Abstract base class for metadata builders.

    Generics:
        T: Dataset type
    """

    @abstractmethod
    def build(self, dataset: T) -> str:
        """
        Generate metadata for dataset.

        Args:
            dataset: Dataset to process (InputDataset or derived)

        Returns:
            String with metadata (XML, JSON, etc.)
        """
        raise NotImplementedError
