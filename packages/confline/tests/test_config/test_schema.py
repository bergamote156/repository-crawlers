"""
Tests for the schema layer: `opt()`, `ConfigFieldInfo`, `ConfigGroup`,
`ConfigSchema`. These are the data shapes Sources and the parser
builder consume — they must be frozen value records, and `opt()` must
faithfully carry every knob into the resulting field info.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from dataclasses import FrozenInstanceError

import pytest

from confline.config import MISSING_DEFAULT
from confline.config.base import ConfigBase
from confline.config.schema import (
    ConfigFieldInfo,
    ConfigGroup,
    ConfigSchema,
    opt,
)
from confline.sources.cli_source import CliSource
from confline.sources.env_source import EnvSource

# ─────────────────────────────────────────────────────────────────────────────
# opt() — invariants
# ─────────────────────────────────────────────────────────────────────────────


def test_opt_rejects_default_and_factory_together():
    with pytest.raises(ValueError, match="cannot set both default and default_factory"):
        opt(5, default_factory=lambda: 5)


def test_opt_default_factory_only():
    class C(ConfigBase):
        tags: list = opt(default_factory=list)

    f = C.__config_schema__.find_field("tags")
    assert f.default_factory is list
    assert f.has_default


def test_opt_no_default_makes_field_required():
    class C(ConfigBase):
        host: str = opt(description="required")

    f = C.__config_schema__.find_field("host")
    assert f.default_factory is None
    assert not f.has_default


# ─────────────────────────────────────────────────────────────────────────────
# opt() — knobs carried into ConfigFieldInfo
# ─────────────────────────────────────────────────────────────────────────────


def test_opt_carries_description_and_default_value():
    class C(ConfigBase):
        host: str = opt("localhost", description="Server host")

    f = C.__config_schema__.find_field("host")
    assert f.default == "localhost"
    assert f.description == "Server host"


def test_opt_default_description_is_empty_string():
    """Empty description → renderer emits no help line for description.
    `None` would force every `--help` formatter to None-guard; `""` is
    the falsy sentinel by convention."""

    class C(ConfigBase):
        x: int = opt(0)

    f = C.__config_schema__.find_field("x")
    assert f.description == ""


def test_opt_carries_choices_as_iterable():
    class C(ConfigBase):
        mode: str = opt("a", choices=["a", "b", "c"])

    f = C.__config_schema__.find_field("mode")
    assert list(f.choices) == ["a", "b", "c"]


def test_opt_carries_secret_flag():
    class C(ConfigBase):
        a: str = opt("a", secret=True)
        b: str = opt("b")

    schema = C.__config_schema__
    assert schema.find_field("a").secret is True
    assert schema.find_field("b").secret is False


def test_opt_carries_excluded_from_as_frozenset():
    class C(ConfigBase):
        a: str = opt("a", excluded_from=[CliSource])
        b: str = opt("b", excluded_from=[CliSource, EnvSource])

    schema = C.__config_schema__
    assert schema.find_field("a").excluded_from == frozenset({CliSource})
    assert schema.find_field("b").excluded_from == frozenset({CliSource, EnvSource})


def test_opt_carries_validator_callable():
    def _strip(v):
        return v.strip()

    class C(ConfigBase):
        name: str = opt("bob", validator=_strip)

    f = C.__config_schema__.find_field("name")
    assert f.validator is _strip


@pytest.mark.parametrize(
    "value",
    [
        True,
        "use --new-name instead",
    ],
)
def test_opt_carries_deprecated_marker_in_both_forms(value):
    """`deprecated=True` is a bare flag; `deprecated="hint"` carries an
    explanatory string for `--help`. Both shapes must land verbatim in
    `ConfigFieldInfo` so the renderer can branch on truthiness AND
    surface the hint when present."""

    class C(ConfigBase):
        old: str = opt("x", deprecated=value)

    f = C.__config_schema__.find_field("old")
    assert f.deprecated == value


def test_opt_carries_count_metavar_and_show_default():
    class C(ConfigBase):
        verbose: int = opt(0, count=True, metavar="N", show_default=True)

    f = C.__config_schema__.find_field("verbose")
    assert f.is_count is True
    assert f.metavar == "N"
    assert f.show_default is True


# ─────────────────────────────────────────────────────────────────────────────
# opt() — mutable default conversion
# ─────────────────────────────────────────────────────────────────────────────


def test_opt_mutable_list_default_yields_independent_instances():
    """`dataclasses.field` rejects mutable defaults — `opt()` converts
    them to factories so each `C()` gets its own copy. Without this,
    `a.tags.append(...)` would leak into `b.tags`."""

    class C(ConfigBase):
        tags: list = opt(default=[])

    a, b = C(), C()
    a.tags.append("x")
    assert a.tags == ["x"]
    assert b.tags == []


def test_opt_mutable_dict_default_yields_independent_instances():
    class C(ConfigBase):
        meta: dict = opt(default={})

    a, b = C(), C()
    a.meta["k"] = 1
    assert a.meta == {"k": 1}
    assert b.meta == {}


def test_opt_mutable_set_default_yields_independent_instances():
    """`set` is in `_is_known_mutable` next to `list`/`dict` — same
    contract, no asymmetry."""

    class C(ConfigBase):
        seen: set = opt(default=set())

    a, b = C(), C()
    a.seen.add("x")
    assert a.seen == {"x"}
    assert b.seen == set()


def test_opt_mutable_default_preserves_initial_contents():
    """The factory captures the original value at `opt()` call time,
    matching Python default-arg semantics — `opt(default=["a"])`
    consistently hands out a fresh `["a"]` per instance."""

    class C(ConfigBase):
        tags: list = opt(default=["a", "b"])

    assert C().tags == ["a", "b"]
    assert C().tags == ["a", "b"]
    a = C()
    a.tags.append("c")
    assert a.tags == ["a", "b", "c"]
    assert C().tags == ["a", "b"]


# ─────────────────────────────────────────────────────────────────────────────
# ConfigFieldInfo
# ─────────────────────────────────────────────────────────────────────────────


def test_config_field_info_is_frozen():
    """`ConfigFieldInfo` is the canonical per-field shape passed to
    Sources. Freezing rules out accidental mutation when a Source
    builds a per-field view via `dataclasses.replace`."""

    class C(ConfigBase):
        x: int = opt(0)

    f = C.__config_schema__.find_field("x")
    with pytest.raises(FrozenInstanceError):
        f.name = "other"  # type: ignore[misc]


def test_has_default_true_when_static_default_present():
    class C(ConfigBase):
        x: int = opt(7)

    assert C.__config_schema__.find_field("x").has_default is True


def test_has_default_true_when_factory_present():
    class C(ConfigBase):
        items: list = opt(default_factory=list)

    field = C.__config_schema__.find_field("items")
    assert field.default is MISSING_DEFAULT
    assert field.default_factory is list
    assert field.has_default is True


def test_has_default_false_when_neither_default_nor_factory():
    class C(ConfigBase):
        host: str = opt(description="required")

    field = C.__config_schema__.find_field("host")
    assert field.default is MISSING_DEFAULT
    assert field.has_default is False


# ─────────────────────────────────────────────────────────────────────────────
# ConfigGroup
# ─────────────────────────────────────────────────────────────────────────────


def test_config_group_is_frozen():
    g = ConfigGroup(name="G", description=None, fields=())
    with pytest.raises(FrozenInstanceError):
        g.name = "other"  # type: ignore[misc]


def test_config_group_defaults_to_non_mutex():
    """A plain group is not a mutex — `is_mutex=True` is opt-in via
    `MutuallyExclusiveGroup`."""
    g = ConfigGroup(name="G", description=None, fields=())
    assert g.is_mutex is False
    assert g.mutex_required is False


# ─────────────────────────────────────────────────────────────────────────────
# ConfigSchema
# ─────────────────────────────────────────────────────────────────────────────


def test_config_schema_is_frozen():
    class C(ConfigBase):
        x: int = opt(0)

    with pytest.raises(FrozenInstanceError):
        C.__config_schema__.config_class = object  # type: ignore[misc]


def test_find_field_returns_field_info_for_known_name():
    class C(ConfigBase):
        host: str = opt("localhost")

    field = C.__config_schema__.find_field("host")
    assert isinstance(field, ConfigFieldInfo)
    assert field.name == "host"


def test_find_field_returns_none_for_unknown_name():
    """Lookup is by-name, not raise-on-miss — callers branch on `None`
    rather than wrapping every call in try/except."""

    class C(ConfigBase):
        host: str = opt("localhost")

    assert C.__config_schema__.find_field("nope") is None


def test_all_fields_iterates_across_groups_in_order():
    """Inheritance produces multiple groups in MRO order; `all_fields`
    flattens them preserving that order so renderers don't need to walk
    `groups` themselves."""

    class A(ConfigBase):
        a: int = opt(1)

    class B(ConfigBase):
        b: int = opt(2)

    class C(A, B):
        c: int = opt(3)

    schema: ConfigSchema = C.__config_schema__
    assert [f.name for f in schema.all_fields()] == ["c", "a", "b"]
