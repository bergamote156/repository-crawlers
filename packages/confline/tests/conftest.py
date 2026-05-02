"""
Pytest configuration shared across the suite.

Re-exports the helpers from `tests/helpers/` as fixtures so tests can
use them without importing — the helpers double as plain callables for
imperative use inside test bodies.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import logging
from collections.abc import Iterator

import pytest

from tests.helpers.fixtures import (
    make_env_source,
    make_namespace,
    make_yaml_source,
    schema_from,
)


@pytest.fixture
def ns_factory():
    """Build an `argparse.Namespace` from kwargs keyed by dotted paths."""
    return make_namespace


@pytest.fixture
def yaml_source_factory():
    """Wrap a dict (or list of dicts) as a `YamlSource`."""
    return make_yaml_source


@pytest.fixture
def env_source_factory():
    """Wrap a dict as an `EnvSource` with optional prefix/delimiter."""
    return make_env_source


@pytest.fixture
def schema_of():
    """Return the `ConfigSchema` of a config class."""
    return schema_from


@pytest.fixture
def capture_logs() -> Iterator[list[logging.LogRecord]]:
    """Capture log records emitted by the `confline` logger."""
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append
    logger = logging.getLogger("confline")
    logger.addHandler(handler)
    prior_level = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prior_level)
