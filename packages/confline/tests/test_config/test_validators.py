"""
Tests for field_validator, model_validator, and opt(validator=…) behaviours.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import pytest

from confline import ConfigBase, DefaultSource, EnvSource, load_config, opt
from confline.config.validators import field_validator, model_validator
from confline.errors import SourceValueError

# ─────────────────────────────────────────────────────────────────────────────
# opt validators
# ─────────────────────────────────────────────────────────────────────────────


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


def test_opt_validator_can_transform_value():
    def _strip(v):
        return v.strip()

    class C(ConfigBase):
        name: str = opt("  bob  ", validator=_strip)

    cfg = load_config(C, sources=[DefaultSource()])
    assert cfg.name == "bob"


# ─────────────────────────────────────────────────────────────────────────────
# field validators
# ─────────────────────────────────────────────────────────────────────────────


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


def test_field_validator_key_error_translated_to_source_value_error():
    lookup = {"a": 1, "b": 2}

    class C(ConfigBase):
        name: str = opt("a")

        @field_validator("name")
        def _check(self, value):
            return lookup[value]  # KeyError on unknown name

    with pytest.raises(SourceValueError):
        load_config(C, sources=[EnvSource({"NAME": "missing"}), DefaultSource()])


def test_field_validator_returning_wrong_type_is_passed_through():
    """Validators are post-coerce user code — a validator returning a
    value of the "wrong" type is not re-coerced or re-validated. This
    pins the contract so a future refactor cannot silently change it."""

    class C(ConfigBase):
        port: int = opt(8080)

        @field_validator("port")
        def _normalize(self, value):
            return f"port-{value}"  # returns str, not int

    cfg = load_config(C, sources=[DefaultSource()])
    assert cfg.port == "port-8080"  # type: ignore[comparison-overlap]


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


def test_single_validator_applies_to_multiple_fields():
    class C(ConfigBase):
        a: str = opt("a")
        b: str = opt("b")

        @field_validator("a", "b")
        def _uppercase(self, v):
            return v.upper()

    cfg = load_config(C, sources=[DefaultSource()])
    assert cfg.a == "A"
    assert cfg.b == "B"


def test_field_validators_parent_runs_before_child():
    fire_order: list[str] = []

    class Parent(ConfigBase):
        x: int = opt(1)

        @field_validator("x")
        def _parent_check(self, v):
            fire_order.append("parent")
            return v

    class Child(Parent):
        @field_validator("x")
        def _child_check(self, v):
            fire_order.append("child")
            return v

    load_config(Child, sources=[DefaultSource()])
    assert fire_order == ["parent", "child"]


def test_field_validator_subclass_override_replaces_parent():
    fire_order: list[str] = []

    class Parent(ConfigBase):
        x: int = opt(1)

        @field_validator("x")
        def _check(self, v):
            fire_order.append("parent")
            return v

    class Child(Parent):
        @field_validator("x")
        def _check(self, v):  # override
            fire_order.append("child")
            return v

    load_config(Child, sources=[DefaultSource()])
    assert fire_order == ["child"]


# ─────────────────────────────────────────────────────────────────────────────
# model validators
# ─────────────────────────────────────────────────────────────────────────────


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


def test_model_validators_respect_declaration_order():
    fire_order: list[str] = []

    class C(ConfigBase):
        x: int = opt(1)

        @model_validator
        def _first(self):
            fire_order.append("first")

        @model_validator
        def _second(self):
            fire_order.append("second")

    load_config(C, sources=[DefaultSource()])
    assert fire_order == ["first", "second"]


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


# ─────────────────────────────────────────────────────────────────────────────
# ordering
# ─────────────────────────────────────────────────────────────────────────────


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
