"""
Tests for `help_text` (one-line `help=` string) and `ConflineHelpFormatter`
(per-field metadata + tag lines).

`help_text` is intentionally minimal — argparse's wrapper handles
descriptions on a single line. The metadata + tag block lives in
`ConflineHelpFormatter._rich_format_action` and is exercised through
`parser.format_help()` snapshots.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from typing import Annotated

import pytest

from confline import (
    ConfigBase,
    DefaultSource,
    EnvSource,
    MutuallyExclusiveGroup,
    YamlSource,
    opt,
)
from confline.sources.cli_source import CliAlias
from confline.ui import build_argparse_parser
from confline.ui.help_format import help_text


@pytest.fixture(autouse=True)
def _no_color(monkeypatch):
    """Disable colour for the duration of one test so `format_help()`
    snapshots match plain text. Scoped per-test via `monkeypatch` so
    no other suite inherits the env var."""
    monkeypatch.setenv("NO_COLOR", "1")


def _field(cls, name):
    return cls.__config_schema__.find_field(name)


def _format_help(cfg_class, *, label_sources=()):
    """Build a parser with default columns and capture `format_help()` text."""
    parser = build_argparse_parser(cfg_class, label_sources=label_sources)
    return parser.format_help()


# ─────────────────────────────────────────────────────────────────────────────
# help_text — one-liner only, no default/env/tag suffixes
# ─────────────────────────────────────────────────────────────────────────────


def test_help_text_with_only_description():
    class C(ConfigBase):
        host: str = opt("localhost", description="Server host")

    assert help_text(_field(C, "host")) == "Server host"


def test_help_text_no_default_suffix_default_now_in_formatter():
    """Earlier confline appended `(default: X)` here; the new
    formatter renders defaults on a separate line, so help_text is
    description-only."""

    class C(ConfigBase):
        port: int = opt(8080, description="Port", show_default=True)

    assert help_text(_field(C, "port")) == "Port"


def test_help_text_count_field_advertises_stacking():
    class C(ConfigBase):
        verbose: int = opt(0, description="Be loud.", count=True)

    assert "stackable" in help_text(_field(C, "verbose"))


def test_help_text_empty_when_no_description_and_no_count():
    class C(ConfigBase):
        x: int = opt()

    assert help_text(_field(C, "x")) == ""


# ─────────────────────────────────────────────────────────────────────────────
# ConflineHelpFormatter — per-field block
# ─────────────────────────────────────────────────────────────────────────────


def test_formatter_renders_default_on_separate_line():
    class C(ConfigBase):
        port: int = opt(8080, description="Port")

    out = _format_help(C)
    assert "--port" in out
    assert "Port" in out
    assert "default: 8080" in out


def test_formatter_redacts_secret_default():
    class C(ConfigBase):
        token: str = opt("real-secret", description="Token", secret=True)

    out = _format_help(C)
    assert "real-secret" not in out
    assert "default: ******" in out
    assert "[secret]" in out


def test_formatter_marks_required_fields():
    class C(ConfigBase):
        host: str = opt(description="required")

    out = _format_help(C)
    assert "default: <required>" in out


def test_formatter_renders_env_and_yaml_lines_when_label_sources_passed():
    class C(ConfigBase):
        port: int = opt(8080, description="Port")

    label_sources = [
        EnvSource({}, prefix="MYAPP_"),
        YamlSource(scopes=()),
        DefaultSource(),
    ]
    out = _format_help(C, label_sources=label_sources)
    # `environment:` is the EnvSource display_label, not the wire-id `env`.
    assert "environment: MYAPP_PORT" in out
    assert "yaml: port" in out
    # Inline metadata layout joins segments with the middle-dot separator.
    assert "default: 8080 · environment: MYAPP_PORT · yaml: port" in out


def test_formatter_uses_custom_source_help_extra_text():
    from confline.sources.base import NO_VALUE, Source

    class VaultSource(Source):
        name = "vault"
        display_label = "vault"

        def resolve(self, field):  # noqa: ARG002
            return NO_VALUE

        def _describe_field(self, field):  # noqa: ARG002
            return "secret/app/port"

    class C(ConfigBase):
        port: int = opt(8080, description="Port")

    out = _format_help(C, label_sources=[VaultSource()])

    assert "vault: secret/app/port" in out


def test_formatter_skips_excluded_source_lines():
    class C(ConfigBase):
        host: str = opt(
            "localhost",
            description="Host",
            excluded_from=[EnvSource],
        )

    out = _format_help(C, label_sources=[EnvSource({}, prefix="APP_"), YamlSource(scopes=())])
    assert "environment:" not in out  # EnvSource is excluded
    assert "yaml: host" in out


def test_formatter_honors_cli_alias_in_action_invocation():
    class C(ConfigBase):
        config_path: Annotated[str, CliAlias("-c", "--config")] = opt("a.yml")

    out = _format_help(C)
    assert "-c" in out
    assert "--config" in out


def test_formatter_renders_factory_default():
    class C(ConfigBase):
        tags: list = opt(default_factory=list, description="Tags")

    out = _format_help(C)
    # Factory rendered as "list()" — never invoked.
    assert "default: list()" in out


def test_formatter_uses_display_label_not_wire_id():
    """Regression — help block rendered `argparse: --port` and
    `env: MYAPP_PORT` even though `display_label` was set to
    `"command line"` and `"environment"`. Renderers must go
    through `display_label`, not `name`. CliSource opts out of the
    help block (`display_in_help_block=False`) so its label only
    shows in the action header — but EnvSource/YamlSource appear
    here and must not leak the wire-id."""

    class C(ConfigBase):
        port: int = opt(8080, description="Port")

    out = _format_help(
        C,
        label_sources=[EnvSource({}, prefix="MYAPP_"), YamlSource(scopes=())],
    )
    assert "environment:" in out
    assert "env: MYAPP_PORT" not in out  # wire-id must not surface


def test_formatter_falls_back_to_no_extras_without_label_sources():
    """Without label_sources the help is still legible — only
    default + tags appear, no env/yaml lines."""

    class C(ConfigBase):
        port: int = opt(8080, description="Port")

    out = _format_help(C)  # no label_sources
    assert "default: 8080" in out
    assert "env:" not in out
    assert "yaml:" not in out


def test_formatter_renders_mutex_tag():
    class Mode(MutuallyExclusiveGroup, required=False):
        json: bool = opt(False, description="JSON output.")
        yaml: bool = opt(False, description="YAML output.")

    out = _format_help(Mode)
    assert "[mutex: Mode]" in out


@pytest.mark.parametrize(
    "counterpart_opt",
    [
        # Sister field has a None default — counts as "no static default",
        # so the field with `8080` uniquely owns the active-by-default slot.
        opt(None, description="Unix socket."),
        # Sister field is required (no default at all) — same conclusion.
        opt(description="Unix socket (required)."),
    ],
    ids=["sister_none", "sister_required"],
)
def test_active_by_default_tag_present_when_only_one_field_has_default(
    counterpart_opt,
):
    """A non-MISSING, non-None default in a mutex group hints to the
    operator that this side runs when nothing is provided. Sister
    fields with `None` or no default at all (`MISSING`) leave the
    one with a real default uniquely active."""

    class Server(MutuallyExclusiveGroup, required=False):
        port: int = opt(8080, description="TCP port.")
        socket: str | None = counterpart_opt

    out = _format_help(Server)

    # Skip the usage line — both flag names appear there too. Body
    # starts at the section header "Server:".
    body = out.split("Server:", 1)[1]
    port_block = body.split("--socket")[0]
    socket_block = body.split("--socket")[1]
    assert "[active by default]" in port_block
    assert "[active by default]" not in socket_block


def test_active_by_default_tag_omitted_when_both_mutex_fields_have_default():
    """If both sides of a mutex have a default, neither should claim
    `[active by default]` — the choice isn't deterministic, and the
    tag would falsely signal "this one runs"."""

    class Server(MutuallyExclusiveGroup, required=False):
        port: int = opt(8080, description="TCP port.")
        socket: str = opt("/tmp/sock", description="Unix socket.")

    out = _format_help(Server)
    assert "[active by default]" not in out


def test_tags_separated_by_middle_dot():
    """Multi-tag lines use ` · ` — visually distinct from inline
    whitespace, so tags read as a list rather than a phrase."""

    class C(ConfigBase):
        token: str = opt(
            "tok",
            description="Token",
            secret=True,
            deprecated=True,
        )

    out = _format_help(C)
    assert "[secret] · [deprecated]" in out


def test_formatter_styles_metadata_segments_with_named_styles(monkeypatch):
    """Defensive: env keys carry `confline.envvar`, yaml keys carry
    `confline.yamlpath`. Without this, a regression that drops the
    `style=` kwarg from `_source_segment` slips through plain-text
    asserts silently. We re-enable colour for this test only — the
    autouse fixture sets `NO_COLOR=1` for plain-text snapshots."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    # Force rich-argparse to render with styles even though stderr is
    # not a tty in the test runner.
    monkeypatch.setenv("FORCE_COLOR", "1")

    class C(ConfigBase):
        port: int = opt(8080, description="Port")

    parser = build_argparse_parser(
        C,
        label_sources=[EnvSource({}, prefix="MYAPP_"), YamlSource(scopes=())],
    )
    rendered = parser.format_help()
    # Style names appear as ANSI escapes in the rendered output. We
    # only need to know that *some* styling was applied — the actual
    # ANSI codes are rich's concern, not ours. The yellow / magenta
    # foreground colours are 33/35 in standard ANSI.
    assert "\x1b[33m" in rendered or "\x1b[93m" in rendered  # yellow / bright_yellow
    assert "\x1b[35m" in rendered or "\x1b[95m" in rendered  # magenta / bright_magenta


def test_formatter_metavar_uses_last_segment_for_nested_field():
    """`--db.url DB.URL` looked like a typo; we now render `--db.url URL`."""

    class Db(ConfigBase):
        url: str = opt("postgres://...", description="DB URL")

    class App(ConfigBase):
        db: Db = opt(default_factory=Db)

    out = _format_help(App)
    assert "--db.url URL" in out
    assert "DB.URL" not in out
