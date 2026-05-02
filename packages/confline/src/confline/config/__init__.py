"""Config building blocks."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from confline.config.base import (
    ConfigBase,
    MutuallyExclusiveGroup,
    is_config_class,
    is_list_of_config_base,
)
from confline.config.types import (
    MISSING_DEFAULT,
    SECRET_PLACEHOLDER,
    FieldPath,
    Provenance,
)
from confline.config.schema import ConfigFieldInfo, ConfigGroup, ConfigSchema, opt
from confline.config.validators import field_validator, model_validator

__all__ = [
    "MISSING_DEFAULT",
    "SECRET_PLACEHOLDER",
    "ConfigBase",
    "ConfigFieldInfo",
    "ConfigGroup",
    "ConfigSchema",
    "FieldPath",
    "MutuallyExclusiveGroup",
    "Provenance",
    "field_validator",
    "is_config_class",
    "is_list_of_config_base",
    "model_validator",
    "opt",
]
