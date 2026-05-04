"""Crawler framework — public API re-exports."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from confline import (
    CliAlias,
    CliSource,
    ConfigBase,
    EnvAlias,
    EnvSource,
    YamlPath,
    YamlSource,
    command,
    field_validator,
    model_validator,
    opt,
)
from confline.sources.cli_source import CliPositional
from crawlers.core.config import (
    CrawlConfig,
    HttpConfig,
    OutputConfig,
    ProcessingConfig,
)
from crawlers.core.http import HttpClient, HttpFailure, ResponseFailure, TimeoutFailure
from crawlers.core.plugin import CrawlerPlugin
from crawlers.core.result import Err, JsonObject, JsonValue, Ok, Result
from crawlers.core.workspace import RunContext

__all__ = [
    # Plugin & command machinery
    "CrawlerPlugin",
    "command",
    # Config schema authoring
    "ConfigBase",
    "opt",
    "field_validator",
    "model_validator",
    # Source-side annotations
    "CliAlias",
    "CliPositional",
    "EnvAlias",
    "YamlPath",
    # Source classes (for `excluded_from=[CliSource]`)
    "CliSource",
    "EnvSource",
    "YamlSource",
    # Config base classes
    "CrawlConfig",
    "HttpConfig",
    "OutputConfig",
    "ProcessingConfig",
    # HTTP
    "HttpClient",
    "HttpFailure",
    "ResponseFailure",
    "TimeoutFailure",
    # Result types
    "Result",
    "Ok",
    "Err",
    "JsonValue",
    "JsonObject",
    # Workspace
    "RunContext",
]
