"""
Source base classes + built-in source implementations.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from confline.sources.base import NO_VALUE, Source
from confline.sources.cli_source import CliAlias, CliPositional, CliSource
from confline.sources.default_source import DefaultSource
from confline.sources.env_source import EnvAlias, EnvSource
from confline.sources.yaml_source import YamlPath, YamlSource

__all__ = [
    "NO_VALUE",
    "CliAlias",
    "CliPositional",
    "CliSource",
    "DefaultSource",
    "EnvAlias",
    "EnvSource",
    "Source",
    "YamlPath",
    "YamlSource",
]
