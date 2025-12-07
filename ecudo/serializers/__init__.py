"""
eCUDO Metadata Serializers

Serializers for converting EcudoRecord to various metadata formats.
"""

from ecudo.serializers.base import MetadataSerializer
from ecudo.serializers.openaire import OpenAIRESerializer

__all__ = ["MetadataSerializer", "OpenAIRESerializer"]
