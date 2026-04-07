"""Default Crawl Specification."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from crawlers.core.api import ApiClient
from crawlers.core.result import Result
from crawlers.processors.parsers import Parser


@dataclass
class DefaultCrawlSpec:
    """
    Everything needed to execute a crawl run.

    Returned by prepare_crawl() and consumed by DefaultCrawlerPlugin.
    The framework opens the client session, builds the pipeline, and
    drives iteration — the plugin only needs to describe what to run.

    Fields:
        client: API client (session opened by the framework via async with)
        iterator_opts: Options passed to client.iterate_datasets(opts, state)
        parser: Transforms raw API items to dataset models

    Optional fields:
        resolve_fn: If provided, the pipeline starts with a DatasetResolver
            (resolve_fn + parser) instead of a plain ParserProcessor.
            Use when the iterator yields partial data (IDs or references)
            that need enrichment via API calls before parsing.
        run_context_name: Used in the run directory name (default: "default")
        banner_subtitle: Shown under the class name in the startup banner
    """

    # pylint: disable=too-many-instance-attributes

    client: ApiClient
    iterator_opts: object
    parser: Parser

    resolve_fn: Callable[[Any], Awaitable[Result[Any, Any]]] | None = None
    run_context_name: str = "default"
    banner_subtitle: str | None = None
