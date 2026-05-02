"""
Test helpers — ergonomic constructors for in-memory sources and schemas.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from argparse import Namespace
from collections.abc import Mapping, Sequence
from typing import Any

from confline.config.base import ConfigBase
from confline.config.schema import ConfigSchema
from confline.sources.cli_source import CliSource
from confline.sources.env_source import EnvSource
from confline.sources.yaml_source import YamlSource


def make_namespace(**kwargs: Any) -> Namespace:
    """Build an `argparse.Namespace` with dotted-path keys.

    `make_namespace(**{"db.host": "localhost"})` builds the namespace
    the parser-builder produces in Step 5.
    """
    ns = Namespace()
    for key, value in kwargs.items():
        setattr(ns, key, value)
    return ns


def make_argparse_source(**kwargs: Any) -> CliSource:
    """Shortcut for `ArgparseSource(make_namespace(**kwargs))`."""
    return CliSource(make_namespace(**kwargs))


def make_yaml_source(data: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> YamlSource:
    """Wrap a dict (or sequence of dicts) as a `YamlSource`."""
    if isinstance(data, Mapping):
        return YamlSource(scopes=[data])
    return YamlSource(scopes=list(data))


def make_env_source(
    data: Mapping[str, str],
    *,
    prefix: str = "",
    delimiter: str = "__",
) -> EnvSource:
    """Wrap a dict as an `EnvSource`."""
    return EnvSource(env=data, prefix=prefix, delimiter=delimiter)


def schema_from(cls: type[ConfigBase]) -> ConfigSchema:
    """Return the `ConfigSchema` for `cls`."""
    return cls.__config_schema__
