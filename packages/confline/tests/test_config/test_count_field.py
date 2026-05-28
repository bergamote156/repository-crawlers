"""
Tests for `opt(count=True)` runtime semantics across sources.

The schema-side contract (count flag carried into `ConfigFieldInfo`)
is in `tests/test_config/test_schema.py`. This file exercises the
runtime path: argparse increments per occurrence, env/yaml deliver
integers, and the resolver rejects boolean values for count fields
(implementation lives in `confline.resolution.resolver`).
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import pytest

from confline import (
    CliSource,
    ConfigBase,
    DefaultSource,
    EnvSource,
    YamlSource,
    load_config,
    opt,
)
from confline.errors import SourceValueError


class _Cfg(ConfigBase):
    verbose: int = opt(0, count=True)


def test_cli_count_increments_per_occurrence():
    src = CliSource.from_argv(_Cfg, ["--verbose", "--verbose", "--verbose"])
    cfg = load_config(_Cfg, sources=[src, DefaultSource()])
    assert cfg.verbose == 3


def test_cli_count_zero_when_flag_absent():
    src = CliSource.from_argv(_Cfg, [])
    cfg = load_config(_Cfg, sources=[src, DefaultSource()])
    assert cfg.verbose == 0


def test_env_count_coerced_as_integer():
    cfg = load_config(_Cfg, sources=[EnvSource({"VERBOSE": "5"}), DefaultSource()])
    assert cfg.verbose == 5


def test_yaml_count_integer_value():
    cfg = load_config(
        _Cfg,
        sources=[YamlSource(scopes=[{"verbose": 7}]), DefaultSource()],
    )
    assert cfg.verbose == 7


def test_yaml_count_boolean_raises_with_count_specific_message():
    with pytest.raises(SourceValueError, match="boolean for a count field"):
        load_config(
            _Cfg,
            sources=[YamlSource(scopes=[{"verbose": True}]), DefaultSource()],
        )


def test_env_count_boolean_string_still_int_coerce_failure():
    """ENV delivers raw strings — `"true"` doesn't satisfy int coerce."""
    with pytest.raises(SourceValueError):
        load_config(_Cfg, sources=[EnvSource({"VERBOSE": "true"}), DefaultSource()])
