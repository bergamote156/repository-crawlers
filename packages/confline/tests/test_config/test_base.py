"""
Tests for `ConfigBase`, `MutuallyExclusiveGroup`, schema build helpers
(`_split_annotated`, `_unwrap_optional`), and the type predicates
(`is_config_class`, `is_list_of_config_base`).

Schema build (`_build_schema`) is exercised through the public surface
of `__config_schema__` rather than imported directly — the contract is
"declare a class, get a schema", not "call _build_schema".
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from typing import Annotated, Optional, Union

from confline.config.base import (
    ConfigBase,
    MutuallyExclusiveGroup,
    _split_annotated,
    _unwrap_optional,
    is_config_class,
    is_list_of_config_base,
)
from confline.config.schema import ConfigFieldInfo, ConfigSchema, opt
from confline.sources.cli_source import CliAlias
from confline.sources.env_source import EnvAlias

# ─────────────────────────────────────────────────────────────────────────────
# Schema build via ConfigBase.__init_subclass__
# ─────────────────────────────────────────────────────────────────────────────


def test_subclass_gets_config_schema_at_class_creation_time():
    """No decorator on user code, no runtime build cost — the schema is
    available the moment the class statement finishes."""

    class C(ConfigBase):
        host: str = opt("localhost")
        port: int = opt(8080)

    schema = C.__config_schema__
    assert isinstance(schema, ConfigSchema)
    assert schema.config_class is C
    assert [f.name for f in schema.all_fields()] == ["host", "port"]
    assert all(isinstance(f, ConfigFieldInfo) for f in schema.all_fields())


def test_field_path_is_singleton_tuple_at_top_level():
    """Top-level fields have a one-element path; the resolver prepends
    parent prefixes when walking nested configs."""

    class C(ConfigBase):
        host: str = opt("localhost")

    f = C.__config_schema__.find_field("host")
    assert f.path == ("host",)


def test_subclass_preserves_user_authored_docstring():
    """`dataclass()` overwrites `__doc__` with an auto-generated
    signature dump that leaks every field's default value. The base
    class restores the original docstring after decoration so help
    renderers and secret-field redaction stay honest."""

    class C(ConfigBase):
        """User-authored doc."""

        secret_token: str = opt("real-secret", secret=True)

    assert C.__doc__ == "User-authored doc."
    # Sanity: dataclass-generated doc would have included the default.
    assert "real-secret" not in (C.__doc__ or "")


def test_subclass_with_no_docstring_keeps_none():
    class C(ConfigBase):
        x: int = opt(0)

    assert C.__doc__ is None


def test_group_description_uses_first_paragraph_only():
    """`--help` shows the group's one-line summary, not the full PEP 257
    docstring. Authors keep details in the body for developer reading;
    the operator-facing render stays tight."""

    class C(ConfigBase):
        """One-line summary.

        Longer body that explains design tradeoffs and is useful for
        developers reading the source — but would crowd the help block.
        """

        x: int = opt(0)

    group = C.__config_schema__.groups[0]
    assert group.description == "One-line summary."


def test_group_description_handles_multiline_first_paragraph():
    """The first paragraph can wrap across multiple lines; only a blank
    line ends it. Newlines inside the paragraph stay collapsed."""

    class C(ConfigBase):
        """Summary that wraps because the
        author indented continuation lines.

        Body paragraph after the blank line.
        """

        x: int = opt(0)

    group = C.__config_schema__.groups[0]
    # `inspect.cleandoc` joins the wrapped lines with `\n`, preserving
    # paragraph structure but removing common indent.
    assert group.description == (
        "Summary that wraps because the\nauthor indented continuation lines."
    )


def test_group_description_none_when_no_docstring():
    class C(ConfigBase):
        x: int = opt(0)

    group = C.__config_schema__.groups[0]
    assert group.description is None


# ─────────────────────────────────────────────────────────────────────────────
# MRO + grouping
# ─────────────────────────────────────────────────────────────────────────────


def test_mro_earliest_definition_wins_on_duplicate_field():
    class A(ConfigBase):
        port: int = opt(1)

    class B(ConfigBase):
        port: int = opt(2)

    class C(A, B):
        pass

    f = C.__config_schema__.find_field("port")
    assert f.default == 1


def test_inheritance_produces_separate_groups_per_class():
    """Each class in the MRO that contributes fields becomes its own
    group, kept distinct so `--help` can section them by origin."""

    class HttpConfig(ConfigBase):
        host: str = opt("localhost")
        port: int = opt(8080)

    class OutputConfig(ConfigBase):
        output_dir: str = opt("/tmp")

    class App(HttpConfig, OutputConfig):
        pass

    schema = App.__config_schema__
    by_name = {g.name: g for g in schema.groups}
    assert {"HttpConfig", "OutputConfig"} <= set(by_name)
    assert [f.name for f in by_name["HttpConfig"].fields] == ["host", "port"]
    assert [f.name for f in by_name["OutputConfig"].fields] == ["output_dir"]


def test_nested_config_field_carries_nested_schema():
    """Nested `ConfigBase` fields stamp the nested schema onto the
    parent field — sources reach into it via `field.nested_schema`
    rather than re-introspecting the type at resolution time."""

    class DbConfig(ConfigBase):
        host: str = opt("localhost")

    class App(ConfigBase):
        db: DbConfig = opt(default_factory=DbConfig)

    f = App.__config_schema__.find_field("db")
    assert f.nested_schema is DbConfig.__config_schema__


# ─────────────────────────────────────────────────────────────────────────────
# Annotated metadata + Optional unwrapping
# ─────────────────────────────────────────────────────────────────────────────


def test_annotated_metadata_carried_verbatim_into_field_info():
    class C(ConfigBase):
        api_key: Annotated[str, EnvAlias("LEGACY_KEY")] = opt("default")

    f = C.__config_schema__.find_field("api_key")
    aliases = [m for m in f.annotated if isinstance(m, EnvAlias)]
    assert len(aliases) == 1
    assert aliases[0].name == "LEGACY_KEY"


def test_multiple_annotated_markers_all_preserved():
    class C(ConfigBase):
        config_path: Annotated[str, CliAlias("-c", "--config"), EnvAlias("CFG")] = opt(
            "default.yaml",
        )

    f = C.__config_schema__.find_field("config_path")
    assert any(isinstance(m, CliAlias) for m in f.annotated)
    assert any(isinstance(m, EnvAlias) for m in f.annotated)


def test_optional_unwraps_to_inner_type_with_is_optional_flag():
    class C(ConfigBase):
        x: int | None = opt(None)
        y: Optional[str] = opt(None)  # noqa: UP045 — exercise the legacy form on purpose

    schema = C.__config_schema__
    fx = schema.find_field("x")
    fy = schema.find_field("y")
    assert fx.field_type is int and fx.is_optional
    assert fy.field_type is str and fy.is_optional


def test_split_annotated_returns_empty_metadata_for_plain_type():
    """The base case keeps `_split_annotated` callable as a generic
    "give me (T, metadata)" helper — non-Annotated input doesn't crash
    and metadata defaults to `()`."""
    inner, meta = _split_annotated(int)
    assert inner is int
    assert meta == ()


def test_unwrap_optional_keeps_two_non_none_union_intact():
    """`int | str | None` has two non-None members — the unwrap rule
    only fires on a single non-None member, so this stays a union and
    `is_optional` reflects None-membership without dropping the union."""
    annotation = Union[int, str, None]  # noqa: UP007 — exercise typing.Union form
    inner, is_optional = _unwrap_optional(annotation)
    assert inner is annotation
    assert is_optional is False


def test_unwrap_optional_passes_plain_type_through():
    inner, is_optional = _unwrap_optional(int)
    assert inner is int
    assert is_optional is False


# ─────────────────────────────────────────────────────────────────────────────
# __repr__ — secret redaction
# ─────────────────────────────────────────────────────────────────────────────


def test_repr_redacts_secret_field_values():
    """`print(config)`, `logger.info('%s', config)`, and `extra={...}`
    all funnel through `__repr__`. Secret fields render as the
    placeholder, not the raw value."""

    class C(ConfigBase):
        host: str = opt("localhost")
        password: str = opt("hunter2", secret=True)
        token: str = opt("abc123", secret=True)

    rendered = repr(C())
    assert "hunter2" not in rendered
    assert "abc123" not in rendered
    assert "******" in rendered
    assert "host='localhost'" in rendered


def test_repr_redacts_secrets_in_nested_config_via_nested_repr():
    """A nested `ConfigBase` has its own `__repr__`; the outer repr
    stringifies the inner via that `__repr__`, so redaction composes
    without the parent needing to know which inner fields are secret."""

    class Inner(ConfigBase):
        api_key: str = opt("topsecret", secret=True)

    class Outer(ConfigBase):
        inner: Inner = opt(default_factory=Inner)

    rendered = repr(Outer())
    assert "topsecret" not in rendered
    assert "******" in rendered


# ─────────────────────────────────────────────────────────────────────────────
# MutuallyExclusiveGroup
# ─────────────────────────────────────────────────────────────────────────────


def test_mutex_subclass_marks_its_own_group_as_mutex():
    class OutputMode(MutuallyExclusiveGroup, required=True):
        json: bool = opt(False)
        yaml: bool = opt(False)

    schema = OutputMode.__config_schema__
    mutex_groups = [g for g in schema.groups if g.is_mutex]
    assert len(mutex_groups) == 1
    assert mutex_groups[0].mutex_required is True


def test_mutex_required_defaults_to_false():
    """`required` is opt-in; default is `at most one` semantics."""

    class Mode(MutuallyExclusiveGroup):
        a: bool = opt(False)
        b: bool = opt(False)

    schema = Mode.__config_schema__
    mutex_groups = [g for g in schema.groups if g.is_mutex]
    assert mutex_groups[0].mutex_required is False


def test_mutex_marker_class_itself_is_not_a_mutex_group():
    """`MutuallyExclusiveGroup` is the marker — only its *subclasses*
    are mutex groups. Detection uses the `__confline_mutex__` attribute
    set in `__init_subclass__`, not an MRO `__name__` check, so a
    rename of the marker class wouldn't silently turn off enforcement."""
    assert MutuallyExclusiveGroup.__confline_mutex__ is False


def test_mutex_subclass_attribute_marks_class_as_mutex():
    class Mode(MutuallyExclusiveGroup):
        a: bool = opt(False)

    assert Mode.__confline_mutex__ is True


# ─────────────────────────────────────────────────────────────────────────────
# is_config_class
# ─────────────────────────────────────────────────────────────────────────────


def test_is_config_class_true_for_configbase_subclass():
    class C(ConfigBase):
        x: int = opt(0)

    assert is_config_class(C) is True


def test_is_config_class_rejects_duck_typed_class():
    """Nominal beats duck — a class with `__config_schema__` but no
    `ConfigBase` parent is rejected so error messages can name the
    contract directly ('must subclass ConfigBase')."""

    class Fake:
        __config_schema__ = "fake"

    assert is_config_class(Fake) is False


def test_is_config_class_rejects_non_types():
    assert is_config_class(42) is False
    assert is_config_class("ConfigBase") is False
    assert is_config_class(None) is False
    assert is_config_class([ConfigBase]) is False


# ─────────────────────────────────────────────────────────────────────────────
# is_list_of_config_base
# ─────────────────────────────────────────────────────────────────────────────


def test_is_list_of_config_base_true_for_list_of_configbase_subclass():
    class Inner(ConfigBase):
        x: int = opt(0)

    assert is_list_of_config_base(list[Inner]) is True


def test_is_list_of_config_base_false_for_list_of_plain_type():
    assert is_list_of_config_base(list[int]) is False


def test_is_list_of_config_base_false_for_dict_of_configbase():
    """Origin must be `list` exactly — `dict[str, ConfigBase]` and
    `tuple[ConfigBase, ...]` don't qualify because the source-side
    handlers built around this predicate only know how to encode the
    list shape."""

    class Inner(ConfigBase):
        x: int = opt(0)

    assert is_list_of_config_base(dict[str, Inner]) is False
    assert is_list_of_config_base(tuple[Inner, ...]) is False


def test_is_list_of_config_base_false_for_bare_list():
    """`list` without args has no element type information — the
    predicate refuses rather than guessing."""
    assert is_list_of_config_base(list) is False


def test_is_list_of_config_base_false_for_non_generic():
    assert is_list_of_config_base(int) is False
    assert is_list_of_config_base(None) is False
