"""
Error rendering for the CLI surface.

Per-error templates (`format_value_error`, `format_missing_required`,
`format_mutex_error`, `format_unknown_command`) plus the closed
`render_for_cli` dispatch and the CommandApp e2e wrapper that
converts framework exceptions into operator-readable stderr messages
with sysexits-keyed exit codes.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from argparse import Namespace

import pytest

from confline import (
    CliSource,
    CommandApp,
    ConfigBase,
    DefaultSource,
    EnvSource,
    MissingRequiredError,
    MutexViolationError,
    MutuallyExclusiveGroup,
    YamlSource,
    command,
    opt,
)
from confline.config.types import SECRET_PLACEHOLDER
from confline.errors import (
    ConfigError,
    MissingFieldRecord,
    ProvidedField,
    SourceValueRecord,
    UnknownCommandError,
)
from confline.ui.errors import (
    _oxford_join,
    format_missing_required,
    format_mutex_error,
    format_unknown_command,
    format_value_error,
    render_for_cli,
)


def _builtin_label_sources():
    """Source chain used by direct format_* tests so the renderer can
    dispatch per-source rendering hooks (T31)."""
    return [
        CliSource(Namespace()),
        EnvSource({}, prefix="MYAPP_"),
        YamlSource(scopes=()),
        DefaultSource(),
    ]


def _provided(  # noqa: PLR0913 — test helper mirroring ProvidedField fields
    path: str,
    source_name: str,
    *,
    value=None,
    key: str | None = None,
    source_label: str | None = None,
    secret: bool = False,
) -> ProvidedField:
    """Compact `ProvidedField` factory for direct error construction."""
    return ProvidedField(
        path=path,
        source_name=source_name,
        source_label=source_label or source_name,
        value=value,
        source_native_key=key,
        secret=secret,
    )


def _has_style(text, style_substring: str) -> bool:
    """True when any span in `text` carries `style_substring` in its style.

    `Text.spans` carries `Style` objects whose `str()` reads like
    `"bold red"` / `"yellow"` — substring matching is enough for the
    defensive checks here. Catches both regressions (style removed)
    and value drift (`yellow` → `bright_yellow`, etc.) without
    pinning the exact style string in test assertions.
    """
    return any(style_substring in str(span.style) for span in text.spans)


# ─────────────────────────────────────────────────────────────────────────────
# render_for_cli — closed dispatch over confline's known error types
# ─────────────────────────────────────────────────────────────────────────────


def test_render_for_cli_falls_back_to_one_line_for_unknown_error():
    """A plain `ConfigError` (no specialised template) renders the
    `prog command: msg` fallback."""
    err = ConfigError("something broke")
    out = render_for_cli(err, prog="myapp", command="serve")
    assert out.plain == "myapp serve: something broke"


def test_render_for_cli_omits_prefix_when_no_prog():
    err = ConfigError("plain")
    assert render_for_cli(err).plain == "plain"


_MUTEX_ERR = MutexViolationError(
    group_name="_Mode",
    field_paths=["port", "socket"],
    provided=[
        _provided("port", "argparse", value=9090, key="--port", source_label="command line"),
        _provided("socket", "env", value="/tmp/x", key="MYAPP_SOCKET", source_label="environment"),
    ],
    required=False,
)
_MISSING_ERR = MissingRequiredError(
    [MissingFieldRecord(path="host", type_desc="string", suggestions=())],
    sources_tried=("env", "default"),
)
_UNKNOWN_ERR = UnknownCommandError("migate", available=("migrate", "serve"), suggestions=("migrate",))


def _format_unknown_command_normalized(err, **kw):
    # format_unknown_command takes `prog` not `command` — adapter to match the shared call shape.
    return format_unknown_command(err, prog=kw.get("prog"))


@pytest.mark.parametrize(
    ("error", "template"),
    [
        (_MUTEX_ERR, format_mutex_error),
        (_MISSING_ERR, format_missing_required),
        (_UNKNOWN_ERR, _format_unknown_command_normalized),
    ],
    ids=["mutex", "missing", "unknown_command"],
)
def test_render_for_cli_dispatches_to_matching_template(error, template):
    """`render_for_cli` on a typed `ConfigError` produces the same
    `Text` as the matching direct `format_*` call — guards against
    dispatch drifting away from the templates."""
    via_dispatch = render_for_cli(error, prog="myapp", command="serve")
    via_template = template(error, prog="myapp", command="serve")
    assert via_dispatch == via_template


# ─────────────────────────────────────────────────────────────────────────────
# format_value_error template
# ─────────────────────────────────────────────────────────────────────────────


def test_format_value_error_renders_template_for_env_failure():
    record = SourceValueRecord(
        path="port",
        type_desc="integer",
        secret=False,
        source_label="env",
        source_native_key="MYAPP_PORT",
        value="abc",
        suggestions=("  --port 8080", "  yaml: `port: 8080`"),
    )
    rendered = format_value_error(record, prog="myapp", command="serve")

    # Header names the failing form (env var) and the prog/command.
    assert rendered.plain.startswith("myapp serve: invalid value for MYAPP_PORT")
    # Body lines.
    assert "  field:    port" in rendered
    assert "  given:    'abc'" in rendered
    assert "  source:   env" in rendered
    assert "  expected: integer" in rendered
    # "Try one of" block lists the pre-computed suggestions.
    assert "Try one of:" in rendered
    assert "--port 8080" in rendered
    assert "yaml: `port: 8080`" in rendered
    # Help footer.
    assert "myapp serve --help" in rendered


def test_format_value_error_redacts_secret_field():
    record = SourceValueRecord(
        path="token",
        type_desc="integer",
        secret=True,
        source_label="env",
        source_native_key=None,
        value="real-secret-not-an-int",
        suggestions=(),
    )
    rendered = format_value_error(record, prog="myapp")
    assert "real-secret" not in rendered
    assert "******" in rendered


def test_format_value_error_without_prog_omits_help_footer():
    record = SourceValueRecord(
        path="port",
        type_desc="integer",
        secret=False,
        source_label="env",
        source_native_key=None,
        value="abc",
        suggestions=(),
    )
    rendered = format_value_error(record)
    assert "--help" not in rendered


def test_format_value_error_header_is_styled_red():
    """Defensive: error message in the header carries `red` styling so
    a future refactor that strips inline styles is caught here.
    Checks the *style*, not the exact colour string — keeps the
    assertion stable across palette tweaks (`red` → `bright_red`)."""
    record = SourceValueRecord(
        path="port",
        type_desc="integer",
        secret=False,
        source_label="env",
        source_native_key="MYAPP_PORT",
        value="abc",
        suggestions=(),
    )
    rendered = format_value_error(record, prog="myapp")
    assert _has_style(rendered, "red")


# ─────────────────────────────────────────────────────────────────────────────
# format_missing_required template
# ─────────────────────────────────────────────────────────────────────────────


def test_format_missing_required_renders_template():
    """Single missing field renders header + body + Try-one-of suggestions
    matching the `format_value_error` template shape."""
    error = MissingRequiredError(
        [
            MissingFieldRecord(
                path="host",
                type_desc="string",
                suggestions=("  MYAPP_HOST=example", "  yaml: `host: example`"),
            )
        ],
        sources_tried=("argparse", "env", "default"),
    )

    out = format_missing_required(error, prog="myapp", command="serve")

    assert out.plain.startswith("myapp serve: missing required field: host")
    assert "  field:    host" in out
    assert "  expected: string" in out
    assert "sources tried: argparse, env, default" in out
    assert "Try one of:" in out
    assert "MYAPP_HOST=" in out
    assert "yaml: `host:" in out
    assert "myapp serve --help" in out


def test_format_missing_required_handles_multiple_fields():
    """Two missing fields produce a header listing both (oxford join)
    and one body block per field."""
    error = MissingRequiredError(
        [
            MissingFieldRecord(
                path="host", type_desc="string", suggestions=("  MYAPP_HOST=example",)
            ),
            MissingFieldRecord(path="port", type_desc="integer", suggestions=("  MYAPP_PORT=0",)),
        ],
        sources_tried=("env", "default"),
    )

    out = format_missing_required(error, prog="myapp", command="serve")

    assert "missing required fields: host and port" in out
    assert "  field:    host" in out
    assert "  field:    port" in out
    assert "MYAPP_HOST=" in out
    assert "MYAPP_PORT=" in out


# ─────────────────────────────────────────────────────────────────────────────
# format_mutex_error template
# ─────────────────────────────────────────────────────────────────────────────


def test_format_mutex_error_too_many_providers_lists_each_with_source():
    error = MutexViolationError(
        group_name="_Mode",
        field_paths=["port", "socket"],
        provided=[
            _provided("port", "argparse", value=9090, key="--port", source_label="command line"),
            _provided(
                "socket", "env", value="/tmp/x", key="MYAPP_SOCKET", source_label="environment"
            ),
        ],
        required=False,
    )
    out = format_mutex_error(
        error,
        prog="myapp",
        command="serve",
        label_sources=_builtin_label_sources(),
    )

    assert "myapp serve:" in out
    assert "port and socket cannot both be set" in out
    assert "(from command line)" in out
    assert "(from environment)" in out
    assert "mutually exclusive" in out


def test_format_mutex_error_renders_values_in_source_native_form():
    """Each provider line carries the value pre-resolved by the loader
    in source-native form (`MYAPP_SOCKET=...`)."""
    error = MutexViolationError(
        group_name="_Mode",
        field_paths=["port", "socket"],
        provided=[
            _provided(
                "socket", "env", value="/tmp/x", key="MYAPP_SOCKET", source_label="environment"
            ),
        ],
        required=False,
    )
    out = format_mutex_error(
        error,
        prog="myapp",
        command="serve",
        label_sources=_builtin_label_sources(),
    )

    assert "MYAPP_SOCKET" in out
    assert "/tmp/x" in out


@pytest.mark.parametrize(
    ("provided", "expected_header", "expected_verb"),
    [
        (
            [
                _provided("port", "argparse", value=9090, key="--port"),
                _provided("socket", "env", value="/tmp/x", key="MYAPP_SOCKET"),
            ],
            "port and socket",
            "cannot both be set",
        ),
        (
            [
                _provided("port", "argparse", value=9090, key="--port"),
                _provided("socket", "env", value="/tmp/x", key="MYAPP_SOCKET"),
                _provided("pipe", "yaml", value="/tmp/p", key="pipe"),
            ],
            "port, socket, and pipe",
            "cannot all be set",
        ),
    ],
)
def test_format_mutex_error_three_field_uses_oxford_comma_and_all(
    provided,
    expected_header,
    expected_verb,
):
    """3+ field groups read naturally: oxford comma + "all" (not "both")."""
    error = MutexViolationError(
        group_name="_OutputModes",
        field_paths=[p.path for p in provided],
        provided=provided,
        required=False,
    )
    out = format_mutex_error(
        error,
        prog="myapp",
        command="serve",
        label_sources=_builtin_label_sources(),
    )
    assert f"{expected_header} {expected_verb}" in out


def test_format_mutex_error_emits_per_source_action_hints():
    """Each provider line carries a channel-specific imperative so an
    operator under deploy pressure doesn't have to google how to unset
    an env var or remove a yaml key."""
    error = MutexViolationError(
        group_name="_OutputModes",
        field_paths=["port", "socket", "pipe"],
        provided=[
            _provided("port", "argparse", value=9090, key="--port", source_label="command line"),
            _provided(
                "socket", "env", value="/tmp/x", key="MYAPP_SOCKET", source_label="environment"
            ),
            _provided("pipe", "yaml", value="/tmp/p", key="pipe", source_label="yaml /etc/app.yml"),
        ],
        required=False,
    )
    out = format_mutex_error(
        error,
        prog="myapp",
        command="serve",
        label_sources=_builtin_label_sources(),
    )

    assert "remove --port" in out
    assert "unset MYAPP_SOCKET" in out
    assert "remove pipe" in out


def test_format_mutex_error_omits_hint_for_unknown_source():
    """When the source could not name the field (key is None), the
    channel-specific hint is suppressed — a generic placeholder would
    mislead the operator. The value line itself still appears."""
    error = MutexViolationError(
        group_name="_Mode",
        field_paths=["port", "socket"],
        provided=[
            _provided("port", "vault", value=9090, key=None),
            _provided("socket", "vault", value="/tmp/x", key=None),
        ],
        required=False,
    )
    out = format_mutex_error(
        error,
        prog="myapp",
        command="serve",
        label_sources=_builtin_label_sources(),
    )

    # Value line still rendered (falls back to dotted path).
    assert "port" in out
    assert "socket" in out
    # No hint — key absent, so we cannot name what to unset.
    assert "unset" not in out
    assert "drop the" not in out
    assert "remove the" not in out


def test_format_mutex_error_required_zero_providers_lists_choices():
    error = MutexViolationError(
        group_name="_RequiredMode",
        field_paths=["a", "b"],
        provided=[],
        required=True,
    )
    out = format_mutex_error(error, prog="myapp", command="serve")

    assert "exactly one of [a, b] must be set" in out
    assert "required mutex group" in out


def test_format_mutex_error_secret_value_is_redacted():
    """A secret field in a mutex group renders as SECRET_PLACEHOLDER —
    the loader pre-redacts the value in `ProvidedField`."""
    error = MutexViolationError(
        group_name="_Tokens",
        field_paths=["token", "key"],
        provided=[
            _provided(
                "token",
                "env",
                value=SECRET_PLACEHOLDER,
                key="MYAPP_TOKEN",
                source_label="environment",
                secret=True,
            ),
            _provided(
                "key",
                "argparse",
                value=SECRET_PLACEHOLDER,
                key="--key",
                source_label="command line",
                secret=True,
            ),
        ],
        required=False,
    )
    out = format_mutex_error(
        error,
        prog="myapp",
        command="serve",
        label_sources=_builtin_label_sources(),
    )

    assert SECRET_PLACEHOLDER in out
    # Secret placeholder rendered bare (no surrounding repr quotes).
    assert f"'{SECRET_PLACEHOLDER}'" not in out


def test_mutex_renderer_falls_back_to_display_label_when_source_label_empty():
    """When `ProvidedField.source_label` is empty, the renderer looks up
    the matching source in `label_sources` and uses its `display_label`.
    This is the contract that lets a custom source declare a clean
    operator-facing label without each provider line re-stating it."""
    from confline.sources.base import NO_VALUE, Source

    class _VaultSource(Source):
        name = "vault"
        display_label = "vault"

        def resolve(self, field):  # noqa: ARG002
            return NO_VALUE

    error = MutexViolationError(
        group_name="_M",
        field_paths=["a", "b"],
        provided=[
            ProvidedField(
                path="a",
                source_name="vault",
                source_label="",
                value="x",
                source_native_key=None,
                secret=False,
            ),
            ProvidedField(
                path="b",
                source_name="vault",
                source_label="",
                value="y",
                source_native_key=None,
                secret=False,
            ),
        ],
        required=False,
    )
    out = format_mutex_error(error, label_sources=[_VaultSource()])
    assert "(from vault)" in out


@pytest.mark.parametrize(
    ("source_name", "expected_style"),
    [("argparse", "cyan"), ("env", "yellow"), ("yaml", "magenta")],
)
def test_format_mutex_error_provider_line_styles_key_per_source(
    source_name,
    expected_style,
):
    """Defensive: provider keys are coloured by source so the visual
    cue matches `help_format` (env=yellow, yaml=magenta, cli=cyan).
    A regression that strips these styles passes plain-text asserts
    silently — this test fails it loudly."""
    error = MutexViolationError(
        group_name="_M",
        field_paths=["a", "b"],
        provided=[
            _provided("a", source_name, value=1, key="--a"),
            _provided("b", source_name, value=2, key="--b"),
        ],
        required=False,
    )
    rendered = format_mutex_error(
        error,
        prog="myapp",
        label_sources=_builtin_label_sources(),
    )
    assert _has_style(rendered, expected_style)


# ─────────────────────────────────────────────────────────────────────────────
# format_unknown_command template
# ─────────────────────────────────────────────────────────────────────────────


def test_format_unknown_command_uses_suggestions_and_available_commands():
    error = UnknownCommandError(
        "migate",
        available=("migrate", "serve"),
        suggestions=("migrate",),
    )

    rendered = format_unknown_command(error, prog="myapp")

    assert rendered.plain.startswith("myapp: unknown command: 'migate'")
    assert "Did you mean:" in rendered
    assert "  migrate" in rendered
    assert "Available commands:" in rendered
    assert "  serve" in rendered
    assert "myapp --help" in rendered


def test_format_unknown_command_section_headers_styled_orange_items_cyan():
    """Defensive: section headers (`Did you mean:`, `Available commands:`)
    use `dark_orange` to match `argparse.groups` in help output, and
    items beneath them use `cyan` to match `argparse.args`. Without
    this assertion a refactor that drops the section helpers passes
    the plain-text checks above silently."""
    error = UnknownCommandError(
        "x",
        available=("serve",),
        suggestions=("serve",),
    )
    rendered = format_unknown_command(error, prog="myapp")
    assert _has_style(rendered, "dark_orange")
    assert _has_style(rendered, "cyan")


# ─────────────────────────────────────────────────────────────────────────────
# Renderer helpers
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        ([], ""),
        (["a"], "a"),
        (["a", "b"], "a and b"),
        (["a", "b", "c"], "a, b, and c"),
        (["a", "b", "c", "d"], "a, b, c, and d"),
    ],
)
def test_oxford_join_handles_n_items(items, expected):
    assert _oxford_join(items) == expected


# ─────────────────────────────────────────────────────────────────────────────
# CommandApp end-to-end (load_config raise → render → sysexits exit code)
# ─────────────────────────────────────────────────────────────────────────────


class _Mode(MutuallyExclusiveGroup, required=False):
    port: int = opt(8080)
    socket: str = opt("/tmp/default")


def test_command_app_renders_mutex_violation_to_stderr_and_exits_usage(
    monkeypatch,
    capsys,
):
    monkeypatch.setenv("MYAPP_SOCKET", "/tmp/x")

    class App(CommandApp):
        prog = "myapp"
        env_prefix = "MYAPP_"

        @command()
        def serve(self, config: _Mode):
            return 0

    with pytest.raises(SystemExit) as excinfo:
        App().run(["serve", "--port", "9090"])
    # MutexViolationError → 64 (EX_USAGE).
    assert excinfo.value.code == 64

    captured = capsys.readouterr()
    assert "myapp serve:" in captured.err
    assert "port and socket cannot both be set" in captured.err
    assert "9090" in captured.err
    assert "/tmp/x" in captured.err


def test_command_app_renders_missing_required_to_stderr_and_exits_usage(capsys):
    """End-to-end: a missing required field surfaces format_missing_required
    on stderr with sysexits EX_USAGE (64), matching mutex-error parity."""

    class Cfg(ConfigBase):
        host: str = opt(description="DB host")

    class App(CommandApp):
        prog = "myapp"

        @command()
        def serve(self, config: Cfg):
            return 0

    with pytest.raises(SystemExit) as excinfo:
        App().run(["serve"])
    assert excinfo.value.code == 64

    captured = capsys.readouterr()
    assert "myapp serve: missing required field: host" in captured.err
    assert "Try one of:" in captured.err
    assert "--host" in captured.err


def test_command_app_renders_value_error_to_stderr_and_exits_dataerr(capsys):
    class Cfg(ConfigBase):
        port: int = opt(8080)

    class App(CommandApp):
        prog = "myapp"

        @command()
        def serve(self, config: Cfg):
            return 0

        # Force a non-CLI source to deliver a bad value: argparse type=
        # would catch this at parse time. Override build_sources to
        # inject a YAML scope with the bad string.
        def build_sources(self, parsed, command):
            yaml = YamlSource(scopes=[{"port": "not-a-number"}])
            base = super().build_sources(parsed, command)
            return [base[0], yaml, *base[1:]]

    with pytest.raises(SystemExit) as excinfo:
        App().run(["serve"])
    # SourceValueError → 65 (EX_DATAERR).
    assert excinfo.value.code == 65

    captured = capsys.readouterr()
    assert "myapp serve:" in captured.err
    assert "field:" in captured.err
    assert "expected:" in captured.err
