"""
Metadata Serializer Base

Abstract base class for metadata serializers.
"""

from abc import ABC, abstractmethod

from ecudo.models.record import EcudoRecord


class MetadataSerializer(ABC):
    """
    Abstract base class for metadata serializers.

    Serializers convert EcudoRecord objects to specific metadata formats
    (XML, JSON-LD, etc.) for registration in various systems.
    """

    @abstractmethod
    def serialize(self, record: EcudoRecord) -> str:
        """
        Serialize an EcudoRecord to the target format.

        Args:
            record: Structured dataset record

        Returns:
            Serialized metadata as string (XML, JSON, etc.)
        """
        pass

    @property
    @abstractmethod
    def format_name(self) -> str:
        """Human-readable name of the format (e.g., 'OpenAIRE v4.0')."""
        pass

    @property
    @abstractmethod
    def content_type(self) -> str:
        """MIME content type (e.g., 'application/xml')."""
        pass
