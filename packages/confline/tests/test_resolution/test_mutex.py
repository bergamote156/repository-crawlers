"""
Post-resolution mutex enforcement.

Argparse's own check fires only at parse time and only on CLI flags.
Confline's check runs after every source has been walked and every
`@model_validator` has had a chance to mutate values, against per-
field provenance.
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
    MutuallyExclusiveGroup,
    YamlSource,
    load_config,
    opt,
)
from confline.errors import ConfigError, MutexViolationError, ProvidedField
from tests.helpers.fixtures import make_argparse_source


class OutputMode(MutuallyExclusiveGroup, required=False):
    json: bool = opt(False)
    yaml: bool = opt(False)
    toml: bool = opt(False)


class StrictMode(MutuallyExclusiveGroup, required=True):
    json: bool = opt(False)
    yaml: bool = opt(False)


def test_mutex_at_most_one_zero_provided_passes():
    cfg = load_config(OutputMode, sources=[DefaultSource()])
    assert cfg.json is False


def test_mutex_at_most_one_single_user_provided_passes():
    cfg = load_config(
        OutputMode,
        sources=[make_argparse_source(json=True), DefaultSource()],
    )
    assert cfg.json is True
    assert cfg.yaml is False


def test_mutex_at_most_one_two_user_provided_yaml_raises():
    """Argparse misses this — YAML provided both, no CLI flag was passed."""
    with pytest.raises(ConfigError, match="at most one"):
        load_config(
            OutputMode,
            sources=[
                YamlSource(scopes=[{"json": True, "yaml": True}]),
                DefaultSource(),
            ],
        )


def test_mutex_violation_records_provenance_per_provided_field():
    """Beyond just raising, the enforcer must populate `provided` with
    structured `ProvidedField` records — `field_paths` keeps the full
    group for the renderer's choice list, and `provided` carries the
    canonical source identity used to dispatch per-source action hints."""
    with pytest.raises(MutexViolationError) as exc:
        load_config(
            OutputMode,
            sources=[
                YamlSource(scopes=[{"json": True, "yaml": True}]),
                DefaultSource(),
            ],
        )
    err = exc.value

    assert err.required is False
    assert err.field_paths == ("json", "yaml", "toml")
    assert {p.path for p in err.provided} == {"json", "yaml"}
    assert {p.source_name for p in err.provided} == {"yaml"}


def test_mutex_at_most_one_two_user_provided_mixed_sources_raises():
    """Each source counts independently — env + yaml = two providers."""
    with pytest.raises(ConfigError, match="at most one"):
        load_config(
            OutputMode,
            sources=[
                EnvSource({"JSON": "true"}),
                YamlSource(scopes=[{"yaml": True}]),
                DefaultSource(),
            ],
        )


def test_mutex_required_zero_provided_raises():
    with pytest.raises(ConfigError, match="exactly one"):
        load_config(StrictMode, sources=[DefaultSource()])


def test_mutex_required_single_provided_passes():
    cfg = load_config(
        StrictMode,
        sources=[YamlSource(scopes=[{"json": True}]), DefaultSource()],
    )
    assert cfg.json is True


def test_mutex_required_two_provided_raises():
    with pytest.raises(ConfigError, match="exactly one"):
        load_config(
            StrictMode,
            sources=[
                YamlSource(scopes=[{"json": True, "yaml": True}]),
                DefaultSource(),
            ],
        )


def test_mutex_via_composition():
    class App(ConfigBase):
        output: OutputMode = opt(default_factory=OutputMode)
        output_dir: str = opt("/tmp")

    # Both nested mutex fields provided via YAML — should fail.
    with pytest.raises(ConfigError, match="at most one"):
        load_config(
            App,
            sources=[
                YamlSource(scopes=[{"output": {"json": True, "yaml": True}}]),
                DefaultSource(),
            ],
        )


def test_mutex_via_composition_zero_provided_no_required_passes():
    class App(ConfigBase):
        output: OutputMode = opt(default_factory=OutputMode)

    cfg = load_config(App, sources=[DefaultSource()])
    assert cfg.output.json is False


def test_mutex_default_value_does_not_count_as_provided():
    """Field at its default (provenance=='default') doesn't count toward mutex."""
    cfg = load_config(
        OutputMode,
        sources=[
            make_argparse_source(json=True),
            DefaultSource(),
        ],
    )
    # json provided via argparse, yaml + toml from defaults — fine.
    assert cfg.json is True
    assert cfg.yaml is False
    assert cfg.toml is False


def test_independent_mutex_groups_enforced_separately():
    class InputMode(MutuallyExclusiveGroup, required=False):
        stdin: bool = opt(False)
        file: bool = opt(False)

    class App(ConfigBase):
        output: OutputMode = opt(default_factory=OutputMode)
        input_: InputMode = opt(default_factory=InputMode)

    # Both groups have at most one user-provided — fine.
    cfg = load_config(
        App,
        sources=[
            YamlSource(
                scopes=[
                    {"output": {"json": True}, "input_": {"stdin": True}},
                ]
            ),
            DefaultSource(),
        ],
    )
    assert cfg.output.json is True
    assert cfg.input_.stdin is True


def test_argparse_still_rejects_two_flags_at_parse_time():
    """Argparse's own mutex check still fires when both flags appear on argv."""
    with pytest.raises(SystemExit):
        CliSource.from_argv(OutputMode, ["--json", "--yaml"])


def test_mutex_required_satisfied_by_yaml_alone():
    """`required=True` accepts YAML-only resolution — argparse no longer
    blocks at parse time, the post-resolution check satisfies it."""
    cfg = load_config(
        StrictMode,
        sources=[YamlSource(scopes=[{"yaml": True}]), DefaultSource()],
    )
    assert cfg.yaml is True


def test_mutex_validator_fix_up_runs_before_check():
    """A @model_validator that normalizes mutex state — but provenance is
    fixed at resolution time and validators don't update it. Behaviour
    documented: validators can mutate values, mutex still counts based on
    original provenance."""
    from confline.config.validators import model_validator

    class Mode(MutuallyExclusiveGroup, required=False):
        json: bool = opt(False)
        yaml: bool = opt(False)

        @model_validator
        def _harmless_normalization(self):
            # No-op for this case; the test just exercises that mutex
            # check doesn't fire on validator-set values.
            pass

    cfg = load_config(Mode, sources=[DefaultSource()])
    assert cfg.json is False


def test_mutex_detection_survives_renaming_marker_class():
    """Mutex detection reads `__confline_mutex__`, not the marker
    class's `__name__` — aliasing/renaming the base must not silently
    disable enforcement."""
    AliasedMutex = MutuallyExclusiveGroup  # noqa: N806 — a local alias mimics rename.

    class Renamed(AliasedMutex, required=False):
        a: bool = opt(False)
        b: bool = opt(False)

    assert Renamed.__confline_mutex__ is True
    with pytest.raises(ConfigError, match="at most one"):
        load_config(
            Renamed,
            sources=[YamlSource(scopes=[{"a": True, "b": True}]), DefaultSource()],
        )


def test_mutex_redacts_secret_field_value_in_provided_record():
    """A secret field caught in a mutex violation must render as the
    redaction placeholder, not the raw value — `ProvidedField.value`
    is what the error renderer prints, so a leak here would surface in
    stderr and structured logs."""
    from confline.config.types import SECRET_PLACEHOLDER

    class Tokens(MutuallyExclusiveGroup, required=False):
        primary: str = opt("", secret=True)
        secondary: str = opt("", secret=True)

    with pytest.raises(MutexViolationError) as exc:
        load_config(
            Tokens,
            sources=[
                YamlSource(scopes=[{"primary": "real-token-A", "secondary": "real-token-B"}]),
                DefaultSource(),
            ],
        )

    err = exc.value
    assert {p.path for p in err.provided} == {"primary", "secondary"}
    for provided in err.provided:
        assert provided.secret is True
        assert provided.value == SECRET_PLACEHOLDER
    # Defence-in-depth: the raw values must not survive anywhere on the error.
    assert "real-token-A" not in str(err)
    assert "real-token-B" not in str(err)


def test_mutex_violation_error_does_not_hold_config_instance():
    """`MutexViolationError` is self-contained — no `instance` field
    pinning a `ConfigBase` reference into the exception graph (Sentry
    captures, GC retention)."""
    error = MutexViolationError(
        group_name="_Mode",
        field_paths=["port", "socket"],
        provided=[
            ProvidedField(
                path="port",
                source_name="argparse",
                source_label="command line",
                value=9090,
                source_native_key="--port",
                secret=False,
            ),
        ],
        required=False,
    )
    assert not hasattr(error, "instance")


def test_value_at_path_returns_none_when_intermediate_is_none():
    """Defensive helper used by `_build_provided_field`: if a model
    validator (or future code path) leaves an `Optional[NestedConfig]`
    set to None, mutex enforcement must not crash on `getattr(None, ...)`.
    The walk short-circuits at the None and returns it, collapsing the
    leaf to 'effectively unset' for the mutex counter."""
    from confline.resolution.mutex import _value_at_path

    class DeepCfg(ConfigBase):
        leaf: bool = opt(False)

    class App(ConfigBase):
        deep: DeepCfg | None = opt(None)

    cfg = App()
    cfg.deep = None  # mimic post-resolution mutation
    assert _value_at_path(cfg, ("deep", "leaf")) is None


def test_value_at_path_returns_value_for_present_path():
    from confline.resolution.mutex import _value_at_path

    class DeepCfg(ConfigBase):
        leaf: bool = opt(False)

    class App(ConfigBase):
        deep: DeepCfg = opt(default_factory=DeepCfg)

    cfg = App()
    cfg.deep.leaf = True
    assert _value_at_path(cfg, ("deep", "leaf")) is True
