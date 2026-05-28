"""
Tests for `DefaultSource` — last source in the chain, surfaces the
field's declared default or `default_factory`.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from confline.config.base import ConfigBase
from confline.config.schema import opt
from confline.sources.base import NO_VALUE
from confline.sources.default_source import DefaultSource


class _Cfg(ConfigBase):
    a: int = opt(5)
    required: int = opt()
    items: list = opt(default_factory=list)


def _f(name: str):
    return _Cfg.__config_schema__.find_field(name)


def test_resolve_returns_declared_default():
    assert DefaultSource().resolve(_f("a")) == 5


def test_resolve_returns_no_value_for_required_field():
    """A required field has no default and no factory — `DefaultSource`
    must surface this as `NO_VALUE` so the resolver can raise
    `MissingRequiredError` rather than fabricating a value."""
    assert DefaultSource().resolve(_f("required")) is NO_VALUE


def test_default_factory_runs_per_resolve():
    """Each `resolve` calls the factory afresh — two list defaults are
    distinct objects, so config instances cannot share mutable state
    through their declared defaults."""
    src = DefaultSource()
    one = src.resolve(_f("items"))
    two = src.resolve(_f("items"))
    assert one == [] and two == []
    assert one is not two


def test_describe_field_returns_none():
    """Defaults are not user-providable through any key — they show as
    the `default:` line in `--help`, not a 'set via' label."""
    assert DefaultSource().describe_field(_f("a")) is None
