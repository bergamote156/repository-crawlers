"""
Exception hierarchy for confline.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from confline.errors.base import ConfigError
from confline.errors.commands import CommandRegistrationError, UnknownCommandError
from confline.errors.env import EnvKeyCollisionError
from confline.errors.resolution import (
    MissingFieldRecord,
    MissingRequiredError,
    MutexViolationError,
    ProvidedField,
    SourceValueError,
    SourceValueRecord,
)
from confline.errors.yaml import (
    ConfigFileNotFoundError,
    YamlParseError,
    YamlPathCollisionError,
    YamlSchemaError,
    YamlSizeLimitError,
)

__all__ = [
    "CommandRegistrationError",
    "ConfigError",
    "ConfigFileNotFoundError",
    "EnvKeyCollisionError",
    "MissingFieldRecord",
    "MissingRequiredError",
    "MutexViolationError",
    "ProvidedField",
    "SourceValueError",
    "SourceValueRecord",
    "UnknownCommandError",
    "YamlParseError",
    "YamlPathCollisionError",
    "YamlSchemaError",
    "YamlSizeLimitError",
]
