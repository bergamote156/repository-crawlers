"""
Tests for value coercion and the type-spec registry that drives both
`coerce()` and the operator-facing copy (`describe_field_type`,
`example_value_for`).
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from collections.abc import Mapping
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Literal
from uuid import UUID

import pytest

from confline import ConfigBase, opt
from confline.resolution.coerce import (
    coerce,
    container_info,
    describe_field_type,
    example_value_for,
    infer_choices,
    register_type,
)


class Role(Enum):
    ADMIN = "admin"
    USER = "user"


def test_none_passthrough():
    assert coerce(None, int) is None


def test_int_from_string():
    assert coerce("42", int) == 42


def test_int_rejects_bool():
    with pytest.raises(ValueError):
        coerce(True, int)


def test_float_from_string():
    assert coerce("3.14", float) == pytest.approx(3.14)


def test_str_passthrough():
    assert coerce("hello", str) == "hello"


def test_str_from_int():
    assert coerce(42, str) == "42"


def test_path_from_string():
    assert coerce("/tmp/foo", Path) == Path("/tmp/foo")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("true", True),
        ("True", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("False", False),
        ("0", False),
        ("no", False),
        ("off", False),
    ],
)
def test_bool_string_recognition(raw, expected):
    assert coerce(raw, bool) is expected


def test_bool_rejects_unknown_string():
    with pytest.raises(ValueError):
        coerce("maybe", bool)


def test_bool_passthrough():
    assert coerce(True, bool) is True
    assert coerce(False, bool) is False


def test_register_type_extension_point():
    class Token:
        def __init__(self, raw: str) -> None:
            self.raw = raw

        def __eq__(self, other):
            return isinstance(other, Token) and other.raw == self.raw

    register_type(Token, Token)
    assert coerce("abc", Token) == Token("abc")


def test_register_type_defaults_description_and_example_when_omitted():
    """`register_type(target, parser)` without `description`/`example`
    falls back to `target.__name__` and `<value>`. Types that need
    nicer rendering should pass them; the defaults keep the registry
    valid so the renderer never has to None-guard."""

    class Token:
        def __init__(self, raw: str) -> None:
            self.raw = raw

    register_type(Token, Token)

    class C(ConfigBase):
        t: Token = opt(default_factory=lambda: Token(""))

    field = C.__config_schema__.find_field("t")
    assert describe_field_type(field) == "Token"
    # No declared default (factory only) and Token's spec example defaults to "<value>".
    assert example_value_for(field) == "<value>"


def test_confline_convert_protocol():
    class Color:
        def __init__(self, name: str):
            self.name = name

        @classmethod
        def __confline_convert__(cls, raw: str) -> "Color":
            return cls(raw.lower())

        def __eq__(self, other):
            return isinstance(other, Color) and other.name == self.name

    assert coerce("RED", Color) == Color("red")


def test_unknown_target_returns_value_unchanged():
    sentinel = object()
    assert coerce(sentinel, object) is sentinel


def test_coerce_passes_value_through_for_non_type_target():
    """`coerce(value, target)` with a `target` that isn't a `type`
    (e.g. a plain string) returns the value unchanged — the registry
    is keyed by classes, and exotic targets shouldn't crash the
    pipeline."""
    sentinel = object()
    assert coerce(sentinel, "not-a-type") is sentinel  # type: ignore[arg-type]


# ─── Enum ───


def test_enum_by_value():
    assert coerce("admin", Role) is Role.ADMIN


def test_enum_by_name_fallback():
    assert coerce("ADMIN", Role) is Role.ADMIN


def test_enum_already_typed_passes_through():
    assert coerce(Role.USER, Role) is Role.USER


def test_enum_invalid_raises():
    with pytest.raises(ValueError):
        coerce("guest", Role)


# ─── Literal ───


def test_literal_string_member_valid():
    assert coerce("a", Literal["a", "b"]) == "a"


def test_literal_int_coerces_inner_type():
    assert coerce("2", Literal[1, 2, 3]) == 2


def test_literal_invalid_raises():
    with pytest.raises(ValueError):
        coerce("c", Literal["a", "b"])


def test_literal_with_none():
    assert coerce(None, Literal[None, "a"]) is None


# ─── datetime / date / time / UUID ───


def test_date_from_iso_string():
    assert coerce("2026-04-30", date) == date(2026, 4, 30)


def test_datetime_from_iso_string():
    assert coerce("2026-04-30T12:00:00", datetime) == datetime(2026, 4, 30, 12, 0, 0)


def test_time_from_iso_string():
    assert coerce("14:30:00", time) == time(14, 30, 0)


def test_uuid_from_string():
    raw = "12345678-1234-5678-1234-567812345678"
    assert coerce(raw, UUID) == UUID(raw)


def test_already_typed_datetime_passes_through():
    dt = datetime(2026, 1, 1)
    assert coerce(dt, datetime) is dt


# ─── Containers ───


def test_list_int_coerces_each_element():
    assert coerce(["1", "2", "3"], list[int]) == [1, 2, 3]


def test_list_rejects_non_sequence():
    with pytest.raises(ValueError):
        coerce("not-a-list", list[int])


def test_set_rejects_non_sequence():
    with pytest.raises(ValueError):
        coerce("not-a-set", set[int])


def test_tuple_rejects_non_sequence():
    with pytest.raises(ValueError):
        coerce("not-a-tuple", tuple[int, ...])


def test_list_of_enum_coerces_each():
    assert coerce(["admin", "user"], list[Role]) == [Role.ADMIN, Role.USER]


def test_tuple_heterogeneous_per_position():
    assert coerce([1, "a"], tuple[int, str]) == (1, "a")


def test_tuple_heterogeneous_wrong_length_raises():
    with pytest.raises(ValueError):
        coerce([1], tuple[int, str])


def test_tuple_variadic_coerces_all_same_type():
    assert coerce(["1", "2", "3"], tuple[int, ...]) == (1, 2, 3)


def test_set_coerces_and_dedupes():
    assert coerce(["1", "2", "2"], set[int]) == {1, 2}


def test_frozenset_returns_frozenset():
    result = coerce(["1", "2"], frozenset[int])
    assert result == frozenset({1, 2})
    assert isinstance(result, frozenset)


def test_dict_coerces_keys_and_values():
    """Previously fell through and returned the raw YAML dict — values
    stayed as strings even when annotated `dict[str, int]`."""
    result = coerce({"a": "1", "b": "2"}, dict[str, int])
    assert result == {"a": 1, "b": 2}
    assert all(isinstance(v, int) for v in result.values())


def test_dict_rejects_non_mapping():
    with pytest.raises(ValueError):
        coerce(["a", 1], dict[str, int])


def test_mapping_annotation_coerces_too():
    result = coerce({"x": "10"}, Mapping[str, int])
    assert result == {"x": 10}


def test_dict_without_type_args_passes_through():
    result = coerce({"a": "1"}, dict)
    assert result == {"a": "1"}  # no args → no inner coercion


# ─── Inference helpers ───


def test_infer_choices_for_enum():
    assert infer_choices(Role) == list(Role)


def test_infer_choices_for_literal():
    assert infer_choices(Literal["a", "b"]) == ["a", "b"]


def test_infer_choices_for_other_returns_none():
    assert infer_choices(int) is None


def test_container_info_for_list():
    origin, args = container_info(list[int])
    assert origin is list
    assert args == (int,)


def test_container_info_for_scalar_is_empty():
    origin, args = container_info(int)
    assert origin is None
    assert args == ()


# ─── Type description helpers ───


def test_describe_field_type_for_built_ins():
    class C(ConfigBase):
        port: int = opt(8080)
        ratio: float = opt(0.5)
        enabled: bool = opt(True)

    schema = C.__config_schema__
    assert describe_field_type(schema.find_field("port")) == "integer"
    assert describe_field_type(schema.find_field("ratio")) == "number"
    assert describe_field_type(schema.find_field("enabled")) == "true or false"


def test_describe_field_type_for_literal_lists_members():
    class C(ConfigBase):
        mode: Literal["fast", "slow"] = opt("fast")

    f = C.__config_schema__.find_field("mode")
    rendered = describe_field_type(f)
    assert rendered.startswith("one of:")
    assert "'fast'" in rendered
    assert "'slow'" in rendered


def test_describe_field_type_for_path():
    class C(ConfigBase):
        out: Path = opt(Path("."))

    assert describe_field_type(C.__config_schema__.find_field("out")) == "path"


@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        (list[int], "list of values"),
        (set[int], "set of values"),
        (frozenset[int], "frozenset of values"),
        (tuple[int, str], "tuple of values"),
        (dict[str, int], "mapping"),
    ],
)
def test_describe_field_type_for_container_origins(annotation, expected):
    """Container annotations render with a generic 'X of values' shape
    so the renderer doesn't have to invent per-element copy. The dict
    annotation collapses to 'mapping' because key+value rendering would
    overwhelm the line."""

    class C(ConfigBase):
        x: annotation = opt(default_factory=annotation)  # type: ignore[misc]

    assert describe_field_type(C.__config_schema__.find_field("x")) == expected


def test_describe_field_type_falls_back_to_class_name_for_unregistered_type():
    """A class with no registered `TypeSpec`, no Enum/Literal shape,
    and no recognised container origin renders as `__name__` — a
    reasonable last-resort label rather than a crash."""

    class _UnknownThing:
        pass

    class C(ConfigBase):
        x: _UnknownThing = opt(default_factory=_UnknownThing)

    assert describe_field_type(C.__config_schema__.find_field("x")) == "_UnknownThing"


def test_example_value_uses_default_when_non_secret():
    class C(ConfigBase):
        port: int = opt(8080)

    assert example_value_for(C.__config_schema__.find_field("port")) == "8080"


def test_example_value_redacts_default_for_secret_field():
    class C(ConfigBase):
        token: str = opt("real-secret", secret=True)

    assert example_value_for(C.__config_schema__.find_field("token")) == "<value>"


def test_example_value_uses_registry_when_no_default():
    """Required field with no default falls back to the type's
    registered example value (`8080` for int) — the operator gets a
    concrete demo even when the field has no declared default."""

    class C(ConfigBase):
        port: int = opt(description="required")

    assert example_value_for(C.__config_schema__.find_field("port")) == "8080"


def test_example_value_falls_back_to_value_placeholder_for_unknown_type():
    """No default, no registry entry → `<value>` placeholder. The
    renderer always has something to print."""

    class _UnknownThing:
        pass

    class C(ConfigBase):
        x: _UnknownThing = opt(description="required")

    assert example_value_for(C.__config_schema__.find_field("x")) == "<value>"
