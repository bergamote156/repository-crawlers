"""
Processor Base

Abstract base class for typed processors.
"""

from abc import ABC, abstractmethod
from typing import Optional


class Processor[I, O](ABC):
    """
    Abstract base class for typed processors.

    Processors transform data in a pipeline. Each processor has:
    - Input type I
    - Output type O
    - Lifecycle methods (open/close)
    - Processing method

    Returning None from process() signals that the item should be
    filtered out (not passed to the next processor).

    Example:
        class MyProcessor(Processor[EcudoDataset, EcudoDataset]):
            async def process(self, item: EcudoDataset) -> Optional[EcudoDataset]:
                if item.title.startswith("Test"):
                    return None  # Filter out
                return item  # Pass through
    """

    async def open(self) -> None:
        """
        Initialize processor resources.

        Called before processing starts. Override to open files,
        create connections, etc.
        """
        return None

    async def close(self) -> None:
        """
        Cleanup processor resources.

        Called after processing ends. Override to close files,
        print statistics, etc.
        """
        return None

    @abstractmethod
    async def process(self, item: I) -> Optional[O]:
        """
        Process a single item.

        Args:
            item: Input item of type I

        Returns:
            Processed item of type O, or None to filter out
        """
        raise NotImplementedError
