"""
Tests for `load_default` and `load_or_exit` — the high-level entry
points that compose Sources + Resolution + UI for non-`CommandApp`
programs.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import pytest

from confline import (
    ConfigBase,
    DefaultSource,
    EnvSource,
    load_default,
    opt,
)
from confline.resolution.api import load_or_exit


class _Cfg(ConfigBase):
    host: str = opt("localhost")
    port: int = opt(8080)


# ─────────────────────────────────────────────────────────────────────────────
# load_default — argv handling
# ─────────────────────────────────────────────────────────────────────────────


def test_load_default_with_argv_none_skips_cli_source(monkeypatch):
    """`argv=None` means no `CliSource` is added to the chain — useful
    for long-lived services that don't accept flags. The env value
    surfaces because nothing higher-priority intervenes."""
    monkeypatch.setenv("MYAPP_PORT", "9090")

    cfg = load_default(_Cfg, env_prefix="MYAPP_")

    assert cfg.port == 9090
    assert cfg.source_of("port").name == "env"


def test_load_default_with_empty_argv_still_adds_cli_source(monkeypatch):
    """`argv=[]` is distinct from `argv=None` — the docstring on
    `load_default` calls this out explicitly. Empty argv enables CLI
    parsing ("no flags provided"), so the chain has CliSource at the
    top even though it resolves nothing."""
    monkeypatch.setenv("MYAPP_PORT", "9090")

    cfg = load_default(_Cfg, env_prefix="MYAPP_", argv=[])

    # Env wins because no flags were given on argv.
    assert cfg.port == 9090
    assert cfg.source_of("port").name == "env"


def test_load_default_with_argv_parses_cli(monkeypatch):
    monkeypatch.setenv("MYAPP_PORT", "9090")

    cfg = load_default(_Cfg, env_prefix="MYAPP_", argv=["--port", "1234"])

    assert cfg.port == 1234
    assert cfg.source_of("port").name == "argparse"


def test_load_default_loads_yaml_when_files_passed(tmp_path):
    cfg_file = tmp_path / "app.yaml"
    cfg_file.write_text("host: from-yaml\n", encoding="utf-8")

    cfg = load_default(_Cfg, yaml_files=[cfg_file])

    assert cfg.host == "from-yaml"
    assert cfg.source_of("host").name == "yaml"


def test_load_default_priority_argv_beats_env_beats_yaml(tmp_path, monkeypatch):
    cfg_file = tmp_path / "app.yaml"
    cfg_file.write_text("host: from-yaml\nport: 1\n", encoding="utf-8")
    monkeypatch.setenv("MYAPP_PORT", "2")

    cfg = load_default(
        _Cfg,
        env_prefix="MYAPP_",
        yaml_files=[cfg_file],
        argv=["--port", "3"],
    )

    assert cfg.port == 3
    assert cfg.host == "from-yaml"


def test_load_default_idempotent_with_stable_env(monkeypatch):
    """Two calls with identical argv + env produce equal configs.
    Guards against future caching mistakes where the second call might
    pick up state mutated between calls. argv+env stable, so nothing
    should change."""
    monkeypatch.setenv("MYAPP_HOST", "h")

    cfg1 = load_default(_Cfg, env_prefix="MYAPP_", argv=["--port", "9090"])
    cfg2 = load_default(_Cfg, env_prefix="MYAPP_", argv=["--port", "9090"])

    assert cfg1.host == cfg2.host == "h"
    assert cfg1.port == cfg2.port == 9090
    assert cfg1.source_of("host").name == cfg2.source_of("host").name == "env"
    assert cfg1.source_of("port").name == cfg2.source_of("port").name == "argparse"


def test_load_default_picks_up_env_changes_between_calls(monkeypatch):
    """Sanity check: the idempotence test above actually exercises live
    env reads. If `load_default` cached the env, mutating it between
    calls would have no effect — and the previous test would still pass
    while masking a regression."""
    monkeypatch.setenv("MYAPP_HOST", "first")
    cfg1 = load_default(_Cfg, env_prefix="MYAPP_")

    monkeypatch.setenv("MYAPP_HOST", "second")
    cfg2 = load_default(_Cfg, env_prefix="MYAPP_")

    assert cfg1.host == "first"
    assert cfg2.host == "second"


# ─────────────────────────────────────────────────────────────────────────────
# load_or_exit — happy path + ConfigError → SystemExit
# ─────────────────────────────────────────────────────────────────────────────


def test_load_or_exit_returns_config_on_success():
    """The happy path is `load_config` plus an empty try clause — the
    config is returned unchanged, no UI side effects."""
    cfg = load_or_exit(_Cfg, sources=[EnvSource({"PORT": "9000"}), DefaultSource()])

    assert cfg.port == 9000
    assert cfg.host == "localhost"


def test_load_or_exit_renders_to_stderr_and_raises_systemexit_on_config_error(capsys):
    """A `ConfigError` (here: invalid value) is rendered to stderr via
    `render_for_cli` and converted into `SystemExit` carrying the
    error's `_EXIT_CODE`. Same path `CommandApp` takes — non-CommandApp
    callers skip the try/except + render + sys.exit boilerplate."""
    with pytest.raises(SystemExit) as exc_info:
        load_or_exit(
            _Cfg,
            sources=[EnvSource({"PORT": "not-an-int"}), DefaultSource()],
            prog="myapp",
        )

    # SourceValueError → 65 (EX_DATAERR).
    assert exc_info.value.code == 65

    captured = capsys.readouterr()
    assert "myapp:" in captured.err
    assert "not-an-int" in captured.err
    # Helpful template output, not just a one-liner.
    assert "field:" in captured.err


def test_load_or_exit_uses_inherited_default_exit_code_for_custom_subclass():
    """A custom `ConfigError` subclass without its own `_EXIT_CODE`
    inherits 78 (EX_CONFIG) from the base — `load_or_exit` reads
    whatever the class chain provides, so framework-misconfig errors
    surface as 'configuration problem, not transient' to a process
    supervisor."""
    from confline.errors import ConfigError
    from confline.sources.base import NO_VALUE, Source

    class _CustomConfigError(ConfigError):
        # No _EXIT_CODE override — inherits 78 from ConfigError.
        pass

    class _RaisingSource(Source):
        name = "raise"
        display_label = "raise"

        def validate_schema(self, schema):  # noqa: ARG002
            raise _CustomConfigError("synthetic failure")

        def resolve(self, field):  # noqa: ARG002
            return NO_VALUE

    with pytest.raises(SystemExit) as exc_info:
        load_or_exit(_Cfg, sources=[_RaisingSource(), DefaultSource()])

    assert exc_info.value.code == 78
