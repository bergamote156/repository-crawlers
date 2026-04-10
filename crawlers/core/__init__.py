"""Crawler framework — public API re-exports."""

from crawlers.core.config import ConfigBase, opt
from crawlers.core.crawl_config import (
    CrawlConfig,
    HttpConfig,
    OutputConfig,
    ProcessingConfig,
)
from crawlers.core.http import HttpClient, HttpFailure, ResponseFailure, TimeoutFailure
from crawlers.core.plugin import CrawlerPlugin, command
from crawlers.core.result import Err, Ok, Result
from crawlers.core.workspace import RunContext

__all__ = [
    "CrawlerPlugin",
    "command",
    "ConfigBase",
    "CrawlConfig",
    "HttpConfig",
    "OutputConfig",
    "ProcessingConfig",
    "opt",
    "HttpClient",
    "HttpFailure",
    "ResponseFailure",
    "TimeoutFailure",
    "Result",
    "Ok",
    "Err",
    "RunContext",
]
