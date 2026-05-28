"""
End-to-end resolution via `load_config`.

Provenance API and cross-source nested resolution have their own homes
(`test_provenance.py`, `test_nested.py`). This file exercises the
resolver's contract: priority order, type coercion failures, secret
redaction, validator wrapping, and source-side eligibility rules.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import pytest

from confline.config.base import ConfigBase
from confline.config.schema import opt
from confline.errors import MissingRequiredError, SourceValueError
from confline.resolution.resolver import load_config
from confline.sources.base import NO_VALUE, Source
from confline.sources.cli_source import CliSource
from confline.sources.default_source import DefaultSource
from confline.sources.env_source import EnvSource
from confline.sources.yaml_source import YamlSource
from tests.helpers.assertions import assert_field_resolved_from
from tests.helpers.fixtures import make_namespace


class FlatCfg(ConfigBase):
    host: str = opt("localhost")
    port: int = opt(8080)
    secret_key: str = opt("default", secret=True, excluded_from=[CliSource])


class DbCfg(ConfigBase):
    host: str = opt("localhost")
    port: int = opt(5432)


class AppCfg(ConfigBase):
    db: DbCfg = opt(default_factory=DbCfg)
    workers: int = opt(4)


# ─────────────────────────────────────────────────────────────────────────────
# Resolution chain — priority and fallthrough
# ─────────────────────────────────────────────────────────────────────────────


def test_default_only_resolution_uses_declared_defaults():
    cfg = load_config(FlatCfg, sources=[DefaultSource()])
    assert cfg.host == "localhost"
    assert cfg.port == 8080
    assert_field_resolved_from(cfg, "host", "default")


def test_higher_priority_source_wins():
    cfg = load_config(
        FlatCfg,
        sources=[
            CliSource(make_namespace(host="from-cli")),
            EnvSource({"HOST": "from-env"}),
            DefaultSource(),
        ],
    )
    assert cfg.host == "from-cli"
    assert_field_resolved_from(cfg, "host", "argparse")


def test_lower_priority_fills_unset_field():
    cfg = load_config(
        FlatCfg,
        sources=[
            CliSource(make_namespace(host="from-cli")),
            EnvSource({"PORT": "9000"}),
            DefaultSource(),
        ],
    )
    assert cfg.host == "from-cli"
    assert cfg.port == 9000
    assert_field_resolved_from(cfg, "host", "argparse")
    assert_field_resolved_from(cfg, "port", "env")


# ─────────────────────────────────────────────────────────────────────────────
# Coercion + null handling — values reaching the dataclass
# ─────────────────────────────────────────────────────────────────────────────


def test_env_value_coerced_to_target_type():
    cfg = load_config(
        FlatCfg,
        sources=[EnvSource({"PORT": "1234"}), DefaultSource()],
    )
    assert cfg.port == 1234
    assert isinstance(cfg.port, int)


def test_coercion_failure_raises_with_field_and_source():
    with pytest.raises(SourceValueError) as exc:
        load_config(
            FlatCfg,
            sources=[EnvSource({"PORT": "abc"}), DefaultSource()],
        )
    assert exc.value.field_record is not None
    assert exc.value.field_record.path == "port"
    assert exc.value.field_record.source_label == "environment"


def test_excluded_source_does_not_resolve_field():
    # secret_key has excluded_from=[CliSource] — argparse should be skipped.
    cfg = load_config(
        FlatCfg,
        sources=[
            CliSource(make_namespace(secret_key="from-cli")),
            EnvSource({"SECRET_KEY": "from-env"}),
            DefaultSource(),
        ],
    )
    assert cfg.secret_key == "from-env"
    assert_field_resolved_from(cfg, "secret_key", "env")


def test_nested_config_resolved_via_recursive_walk():
    cfg = load_config(
        AppCfg,
        sources=[
            YamlSource(scopes=[{"db": {"host": "yaml-host"}, "workers": 8}]),
            EnvSource({"DB__PORT": "6543"}),
            DefaultSource(),
        ],
    )
    assert cfg.db.host == "yaml-host"
    assert cfg.db.port == 6543
    assert cfg.workers == 8
    assert_field_resolved_from(cfg, "db.host", "yaml")
    assert_field_resolved_from(cfg, "db.port", "env")
    assert_field_resolved_from(cfg, "workers", "yaml")


def test_extras_ignore_silent():
    cfg = load_config(
        AppCfg,
        sources=[
            YamlSource(scopes=[{"workers": 4, "rogue": "x"}]),
            DefaultSource(),
        ],
    )
    assert cfg.workers == 4


def test_yaml_explicit_null_overrides_default():
    class C(ConfigBase):
        host: str | None = opt("localhost")

    cfg = load_config(
        C,
        sources=[YamlSource(scopes=[{"host": None}]), DefaultSource()],
    )
    assert cfg.host is None
    assert_field_resolved_from(cfg, "host", "yaml")


def test_yaml_explicit_null_on_non_optional_raises_with_path():
    """`port: null` on a `port: int` field used to crash the dataclass
    __init__ with a context-free TypeError. Now confline catches it."""

    class C(ConfigBase):
        port: int = opt(8080)

    with pytest.raises(SourceValueError) as exc:
        load_config(
            C,
            sources=[YamlSource(scopes=[{"port": None}]), DefaultSource()],
        )
    assert exc.value.field_record is not None
    assert exc.value.field_record.path == "port"
    assert exc.value.field_record.source_label == "yaml"
    assert "non-Optional" in str(exc.value) or "null" in str(exc.value)


# ─────────────────────────────────────────────────────────────────────────────
# Secret redaction — wrapper + chained cause
# ─────────────────────────────────────────────────────────────────────────────


def test_secret_field_redacts_value_in_error():
    class Cfg(ConfigBase):
        port: int = opt(0, secret=True)

    with pytest.raises(SourceValueError) as exc:
        load_config(Cfg, sources=[EnvSource({"PORT": "abc"}), DefaultSource()])
    assert exc.value.field_record is not None
    assert exc.value.field_record.value is None  # redacted


def test_secret_field_redaction_extends_to_exception_chain():
    """Sentry/Datadog formatters walk `__cause__`. For secret fields,
    the raw value must not survive in either the wrapper or the chained
    cause — and the cause's class identity must be preserved so callers
    can still pattern-match on the underlying error type."""

    class Cfg(ConfigBase):
        token: int = opt(secret=True)

    with pytest.raises(SourceValueError) as exc_info:
        load_config(
            Cfg,
            sources=[EnvSource({"TOKEN": "supersecret-not-an-int"})],
        )

    err = exc_info.value
    assert "supersecret" not in str(err)
    cause = err.__cause__
    assert cause is not None
    assert "supersecret" not in str(cause)
    assert isinstance(cause, ValueError)


# ─────────────────────────────────────────────────────────────────────────────
# Typed errors — resolver wraps raw failures with framework context
# ─────────────────────────────────────────────────────────────────────────────


def test_resolver_replaces_dataclass_typeerror_with_typed_missing_required():
    """A required field with no source surfaces a typed
    `MissingRequiredError` naming the field and listing the chain — not
    the dataclass's context-free `TypeError("missing 1 required ...")`."""

    class Cfg(ConfigBase):
        host: str = opt(description="required")

    with pytest.raises(MissingRequiredError) as exc:
        load_config(Cfg, sources=[DefaultSource()])

    err = exc.value
    assert err.fields[0].path == "host"
    assert err.sources_tried == ("default",)


def test_resolver_populates_source_value_record_for_renderer():
    """The loader populates `field_record.path` and `source_label` so
    `format_value_error` can render without re-walking the schema. The
    label is the user-facing channel role (`environment`), not the
    dispatch identity (`env`)."""

    class Cfg(ConfigBase):
        port: int = opt(8080)

    with pytest.raises(SourceValueError) as exc:
        load_config(Cfg, sources=[EnvSource({"PORT": "abc"})])

    err = exc.value
    assert err.field_record is not None
    assert err.field_record.path == "port"
    assert err.field_record.source_label == "environment"


# ─────────────────────────────────────────────────────────────────────────────
# Eligibility — excluded_from + source schema validation
# ─────────────────────────────────────────────────────────────────────────────


def test_loader_skips_sources_listed_in_excluded_from():
    """excluded_from is enforced at the loader before dispatch — sources
    don't have to (and no longer do) self-check. Covers all four
    built-ins in one shot."""

    class Cfg(ConfigBase):
        a: int = opt(0, excluded_from=[CliSource])
        b: int = opt(0, excluded_from=[EnvSource])
        c: int = opt(0, excluded_from=[YamlSource])
        d: int = opt(7, excluded_from=[DefaultSource])

    cfg = load_config(
        Cfg,
        sources=[
            CliSource(make_namespace(a=1, b=2, c=3, d=4)),
            EnvSource({"A": "11", "B": "22", "C": "33", "D": "44"}),
            YamlSource(scopes=[{"a": 111, "b": 222, "c": 333, "d": 444}]),
            DefaultSource(),
        ],
    )
    # `a` skipped argparse → env wins
    assert cfg.a == 11
    # `b` skipped env → argparse wins (argparse is first in the chain)
    assert cfg.b == 2
    # `c` skipped yaml → argparse wins
    assert cfg.c == 3
    # `d` skipped default — but argparse wins anyway
    assert cfg.d == 4


def test_loader_enforces_excluded_from_for_third_party_source():
    """A custom source listed in `excluded_from` is skipped at the loader
    before dispatch — proof the boilerplate lives in one place, not in
    each source."""

    class FakeVault(Source):
        name = "vault"
        display_label = "vault"

        def resolve(self, field):  # noqa: ARG002 — protocol
            return "from-vault"

    class Cfg(ConfigBase):
        token: str = opt("default", excluded_from=[FakeVault])

    cfg = load_config(Cfg, sources=[FakeVault(), DefaultSource()])
    assert cfg.token == "default"


def test_loader_runs_source_schema_validation():
    """Source-specific schema validation runs before resolution."""

    class _ValidatingSource(Source):
        name = "validating"
        display_label = "validating"

        def resolve(self, field):  # noqa: ARG002
            return NO_VALUE

        def validate_schema(self, schema):  # noqa: ARG002
            raise RuntimeError("schema rejected")

    class Cfg(ConfigBase):
        host: str = opt("localhost")

    with pytest.raises(RuntimeError, match="schema rejected"):
        load_config(Cfg, sources=[_ValidatingSource(), DefaultSource()])


# ─────────────────────────────────────────────────────────────────────────────
# Suggestion building — `Try one of` block composition
# ─────────────────────────────────────────────────────────────────────────────


def test_suggestion_build_does_not_mask_coercion_error_when_labeling_fails():
    class _ExplodingLabelSource(Source):
        name = "exploding-label"
        display_label = "exploding-label"

        def resolve(self, field):  # noqa: ARG002
            return NO_VALUE

        def describe_field(self, field):  # noqa: ARG002
            raise RuntimeError("label rendering crashed")

    class Cfg(ConfigBase):
        port: int = opt(8080)

    with pytest.raises(SourceValueError) as exc:
        load_config(
            Cfg,
            sources=[
                EnvSource({"PORT": "not-an-int"}),
                _ExplodingLabelSource(),
                DefaultSource(),
            ],
        )
    assert exc.value.field_record is not None
    assert exc.value.field_record.path == "port"
    # coercion failure stays the primary error despite buggy label rendering
    assert "not-an-int" in str(exc.value)


def test_suggestions_skip_sources_excluded_for_field():
    class _VaultSource(Source):
        name = "vault"
        display_label = "vault"

        def resolve(self, field):  # noqa: ARG002
            return NO_VALUE

        def describe_field(self, field):  # noqa: ARG002
            return "VAULT_PORT"

    class Cfg(ConfigBase):
        port: int = opt(8080, excluded_from=[_VaultSource])

    with pytest.raises(SourceValueError) as exc:
        load_config(
            Cfg,
            sources=[EnvSource({"PORT": "oops"}), _VaultSource(), DefaultSource()],
        )

    assert exc.value.field_record is not None
    # excluded source should not leak into "Try one of" suggestions
    assert all("VAULT_PORT" not in s for s in exc.value.field_record.suggestions)


def test_custom_source_kv_separator_shapes_suggestion_line():
    """Suggestion lines are composed via `source.display_kv_separator`,
    not by branching on `source.name`. A custom source's class-level
    separator controls the shape of its line in the "Try one of" block,
    so plugin sources slot in without resolver-side casework."""

    class _CustomSource(Source):
        name = "custom"
        display_label = "custom"
        display_kv_separator = "##"  # weird separator to make assertion obvious

        def resolve(self, field):  # noqa: ARG002
            return NO_VALUE

        def _describe_field(self, field):
            return f"<custom:{'.'.join(field.path)}>"

    class _FailSource(Source):
        name = "fail"
        display_label = "fail"

        def resolve(self, field):  # noqa: ARG002
            raise ValueError("bad value")

    class Cfg(ConfigBase):
        port: int = opt(8080)

    with pytest.raises(SourceValueError) as exc:
        load_config(Cfg, sources=[_FailSource(), _CustomSource()])

    assert exc.value.field_record is not None
    assert any("<custom:port>##8080" in s for s in exc.value.field_record.suggestions)


def test_custom_source_default_kv_separator_uses_space():
    """A custom source without an explicit `display_kv_separator`
    inherits the base default `" "` — generic but readable."""

    class _BareCustomSource(Source):
        name = "bare"
        display_label = "bare"

        def resolve(self, field):  # noqa: ARG002
            return NO_VALUE

        def _describe_field(self, field):
            return ".".join(field.path)

    class _FailSource(Source):
        name = "fail"
        display_label = "fail"

        def resolve(self, field):  # noqa: ARG002
            raise ValueError("bad value")

    class Cfg(ConfigBase):
        port: int = opt(8080)

    with pytest.raises(SourceValueError) as exc:
        load_config(Cfg, sources=[_FailSource(), _BareCustomSource()])

    assert exc.value.field_record is not None
    assert any("port 8080" in s for s in exc.value.field_record.suggestions)
