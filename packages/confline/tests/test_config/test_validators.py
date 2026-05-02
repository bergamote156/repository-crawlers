"""
Tests for validator decorators + collection helpers.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import pytest

from confline import ConfigBase, DefaultSource, EnvSource, load_config, opt
from confline.config.validators import (
    collect_field_validators,
    collect_model_validators,
    field_validator,
    model_validator,
)
from confline.errors import SourceValueError


def test_model_validator_decorator_marks_method():
    class C:
        @model_validator
        def _check(self):
            pass

    assert C._check.__confline_model_validator__ is True


def test_field_validator_decorator_carries_names():
    class C:
        @field_validator("a", "b")
        def _check(self, v):
            return v

    assert C._check.__confline_field_validator__ == ("a", "b")


def test_collect_model_validators_keeps_declaration_order():
    class C(ConfigBase):
        x: int = opt(1)

        @model_validator
        def _first(self):
            pass

        @model_validator
        def _second(self):
            pass

    assert collect_model_validators(C) == ("_first", "_second")


def test_collect_model_validators_walks_mro_base_first():
    class Parent(ConfigBase):
        @model_validator
        def _parent_check(self):
            pass

    class Child(Parent):
        @model_validator
        def _child_check(self):
            pass

    assert collect_model_validators(Child) == ("_parent_check", "_child_check")


def test_collect_field_validators_groups_per_field():
    class C(ConfigBase):
        a: int = opt(1)
        b: int = opt(2)

        @field_validator("a")
        def _on_a(self, v):
            return v

        @field_validator("b")
        def _on_b(self, v):
            return v

    fv = collect_field_validators(C)
    assert fv == {"a": ("_on_a",), "b": ("_on_b",)}


def test_collect_field_validators_walks_mro_base_first_within_field():
    """A child class may add validators to a field already validated by
    the parent. Within the field bucket, validators appear in
    base-to-derived order so the parent's invariants run first."""

    class Parent(ConfigBase):
        x: int = opt(1)

        @field_validator("x")
        def _parent_check(self, v):
            return v

    class Child(Parent):
        @field_validator("x")
        def _child_check(self, v):
            return v

    fv = collect_field_validators(Child)
    assert fv == {"x": ("_parent_check", "_child_check")}


def test_collect_field_validators_supports_one_method_validating_multiple_fields():
    """`@field_validator("a", "b")` is one method registered against
    two fields. The collector lists it under each field independently
    so the resolver can dispatch the same callable per-field."""

    class C(ConfigBase):
        a: int = opt(1)
        b: int = opt(2)

        @field_validator("a", "b")
        def _shared(self, v):
            return v

    fv = collect_field_validators(C)
    assert fv == {"a": ("_shared",), "b": ("_shared",)}


def test_collect_model_validators_overridden_method_keeps_parent_position():
    """Overriding by name in a subclass keeps the parent's position in
    the order — `getattr` resolves to the most-derived implementation
    at runtime, but the schedule (which slot it occupies) is set when
    the parent first declared it."""

    class Parent(ConfigBase):
        x: int = opt(1)

        @model_validator
        def _check(self):
            pass

        @model_validator
        def _later(self):
            pass

    class Child(Parent):
        @model_validator
        def _check(self):  # override in place
            pass

    assert collect_model_validators(Child) == ("_check", "_later")


def test_opt_validator_runs_during_resolution():
    def _positive(v):
        if v <= 0:
            raise ValueError(f"must be positive, got {v}")
        return v

    class C(ConfigBase):
        port: int = opt(8080, validator=_positive)

    cfg = load_config(C, sources=[DefaultSource()])
    assert cfg.port == 8080

    with pytest.raises(SourceValueError):
        load_config(C, sources=[EnvSource({"PORT": "-1"}), DefaultSource()])


def test_field_validator_assert_statement_translates_to_source_value_error():
    """A user validator written in the natural Python idiom — `assert`
    — raises `AssertionError`, not `ValueError`. The framework must
    catch and wrap that into `SourceValueError` with field context, so
    the user contract is "any raise from a validator surfaces as a
    typed framework error" rather than "remember to raise ValueError"."""

    class C(ConfigBase):
        port: int = opt(8080)

        @field_validator("port")
        def _positive(self, v):
            assert v > 0, "must be positive"  # noqa: S101
            return v

    with pytest.raises(SourceValueError) as exc:
        load_config(C, sources=[EnvSource({"PORT": "-1"}), DefaultSource()])
    assert exc.value.field_record is not None
    assert exc.value.field_record.path == "port"


def test_opt_validator_can_transform_value():
    def _strip(v):
        return v.strip()

    class C(ConfigBase):
        name: str = opt("  bob  ", validator=_strip)

    cfg = load_config(C, sources=[DefaultSource()])
    assert cfg.name == "bob"


def test_field_validator_runs_after_instance_built_with_self():
    captured: list = []

    class C(ConfigBase):
        host: str = opt("LOCALHOST")
        port: int = opt(8080)

        @field_validator("host")
        def _lower_and_remember_port(self, v):
            captured.append(self.port)
            return v.lower()

    cfg = load_config(C, sources=[DefaultSource()])
    assert cfg.host == "localhost"
    # `self` is populated when the validator fires.
    assert captured == [8080]


def test_model_validator_can_mutate_self():
    class C(ConfigBase):
        a: int = opt(1)
        b: int = opt(2)
        total: int = opt(0)

        @model_validator
        def _sum(self):
            self.total = self.a + self.b

    cfg = load_config(C, sources=[DefaultSource()])
    assert cfg.total == 3


def test_model_validator_can_raise_to_abort():
    class C(ConfigBase):
        username: str | None = opt(None)
        password: str | None = opt(None)

        @model_validator
        def _both_or_neither(self):
            if bool(self.username) != bool(self.password):
                raise ValueError("username and password must be set together")

    cfg = load_config(C, sources=[DefaultSource()])
    assert cfg.username is None  # neither set — fine

    with pytest.raises(ValueError, match="must be set together"):
        load_config(
            C,
            sources=[EnvSource({"USERNAME": "alice"}), DefaultSource()],
        )


def test_nested_validators_fire_before_parent():
    fire_order: list[str] = []

    class Inner(ConfigBase):
        @model_validator
        def _inner(self):
            fire_order.append("inner")

    class Outer(ConfigBase):
        inner: Inner = opt(default_factory=Inner)

        @model_validator
        def _outer(self):
            fire_order.append("outer")

    load_config(Outer, sources=[DefaultSource()])
    assert fire_order == ["inner", "outer"]


def test_field_validator_runs_before_model_validator():
    fire_order: list[str] = []

    class C(ConfigBase):
        x: int = opt(1)

        @field_validator("x")
        def _on_x(self, v):
            fire_order.append("field")
            return v

        @model_validator
        def _check(self):
            fire_order.append("model")

    load_config(C, sources=[DefaultSource()])
    assert fire_order == ["field", "model"]


def test_subclass_validator_overrides_parent_via_attribute_lookup():
    fire_order: list[str] = []

    class Parent(ConfigBase):
        x: int = opt(1)

        @model_validator
        def _check(self):
            fire_order.append("parent")

    class Child(Parent):
        @model_validator
        def _check(self):  # override
            fire_order.append("child")

    load_config(Child, sources=[DefaultSource()])
    assert fire_order == ["child"]
