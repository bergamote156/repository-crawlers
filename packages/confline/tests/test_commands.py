"""
Tests for `CommandApp` orchestration.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from pathlib import Path

import pytest

from confline import (
    CommandApp,
    ConfigBase,
    command,
    opt,
)
from confline.errors import (
    CommandRegistrationError,
    ConfigError,
    ConfigFileNotFoundError,
    EnvKeyCollisionError,
    MissingRequiredError,
    MutexViolationError,
    ProvidedField,
    SourceValueError,
    UnknownCommandError,
    YamlParseError,
    YamlSchemaError,
    YamlSizeLimitError,
)
from confline.spec import Command


class _RegConfig(ConfigBase):
    target: str = opt("default")


class _CrawlConfig(ConfigBase):
    plugin: str = opt("all")
    workers: int = opt(4)


def test_command_decorator_derives_kebab_name_from_method():
    @command()
    def my_cmd(self, config: _RegConfig):
        return config.target

    # Default conversion `_` → `-` matches Click/Typer kebab-case CLIs.
    assert my_cmd.__confline_command__["name"] == "my-cmd"
    assert my_cmd.__confline_command__["config_class"] is _RegConfig


def test_command_decorator_bare_works_without_parens():
    @command
    def my_cmd(self, config: _RegConfig):
        return config.target

    assert my_cmd.__confline_command__["name"] == "my-cmd"
    assert my_cmd.__confline_command__["config_class"] is _RegConfig


def test_command_decorator_explicit_name_preserves_underscores():
    @command(name="my_cmd")
    def my_cmd(self, config: _RegConfig):
        return config.target

    assert my_cmd.__confline_command__["name"] == "my_cmd"


def test_command_decorator_explicit_config_class():
    @command(config_class=_RegConfig)
    def my_cmd(self, config):  # no annotation
        return config.target

    assert my_cmd.__confline_command__["config_class"] is _RegConfig


def test_command_decorator_without_annotation_raises():
    with pytest.raises(CommandRegistrationError, match="config_class"):

        @command()
        def my_cmd(self, config):  # no annotation, no explicit
            return config


def test_command_decorator_aliases_carried():
    @command(aliases=["alt", "x"])
    def my_cmd(self, config: _RegConfig):
        return config

    assert my_cmd.__confline_command__["aliases"] == ("alt", "x")


def test_command_description_explicit_wins():
    @command(description="Re-register the dataset.")
    def reg(self, config: _RegConfig):
        """Auto-derived would say this."""
        return config

    assert reg.__confline_command__["description"] == "Re-register the dataset."


def test_command_description_falls_back_to_first_doc_line():
    @command()
    def reg(self, config: _RegConfig):
        """Re-register the dataset.

        Longer multi-line body that should not appear in --help.
        """
        return config

    assert reg.__confline_command__["description"] == "Re-register the dataset."


def test_command_description_empty_when_no_doc_no_explicit():
    @command()
    def reg(self, config: _RegConfig):
        return config

    assert reg.__confline_command__["description"] == ""


def test_command_description_surfaces_in_subparser_help(capsys):
    """Top-level `--help` lists each command with its description."""

    class App(CommandApp):
        prog = "myapp"

        @command(description="Re-register the dataset.")
        def reg(self, config: _RegConfig):
            return config

    rc = App().run([])  # bare invocation prints top-level help
    assert rc == 0
    out = capsys.readouterr().out
    assert "Re-register the dataset." in out


def test_command_app_registers_commands_from_subclass():
    class App(CommandApp):
        @command()
        def reg(self, config: _RegConfig):
            return config

        @command()
        def crawl(self, config: _CrawlConfig):
            return config

    assert set(App._commands.keys()) == {"reg", "crawl"}
    assert isinstance(App._commands["reg"], Command)
    assert App._commands["crawl"].config_class is _CrawlConfig


def test_command_app_alias_resolution():
    class App(CommandApp):
        @command(aliases=["c"])
        def crawl(self, config: _CrawlConfig):
            return config.plugin

    app = App()
    assert app.run(["c", "--plugin", "openaire"]) == "openaire"
    assert app.run(["crawl", "--plugin", "datacite"]) == "datacite"


def test_command_app_dispatches_correct_command():
    class App(CommandApp):
        @command()
        def reg(self, config: _RegConfig):
            return ("reg", config.target)

        @command()
        def crawl(self, config: _CrawlConfig):
            return ("crawl", config.plugin)

    app = App()
    assert app.run(["reg", "--target", "x"]) == ("reg", "x")
    assert app.run(["crawl"]) == ("crawl", "all")


def test_command_app_env_prefix_forwarded(monkeypatch):
    monkeypatch.setenv("MYAPP_TARGET", "from-env")

    class App(CommandApp):
        env_prefix = "MYAPP_"

        @command()
        def reg(self, config: _RegConfig):
            return config.target

    assert App().run(["reg"]) == "from-env"


def test_command_app_config_option_loads_yaml(tmp_path):
    cfg_file = tmp_path / "app.yaml"
    cfg_file.write_text("target: from-yaml\n", encoding="utf-8")

    class App(CommandApp):
        @command()
        def reg(self, config: _RegConfig):
            return config.target

    assert App().run(["-c", str(cfg_file), "reg"]) == "from-yaml"


def test_command_app_bare_invocation_prints_help_and_returns_zero(capsys):
    """First impression of the tool: no command → help + exit 0,
    not "missing required argument: _command"."""

    class App(CommandApp):
        @command()
        def reg(self, config: _RegConfig):
            return config

    rc = App().run([])
    assert rc == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out
    assert "reg" in captured.out  # commands listed


def test_command_app_unknown_command_renders_stderr_and_exits_usage(capsys):
    class App(CommandApp):
        prog = "myapp"

        @command()
        def migrate(self, config: _RegConfig):
            return config

        @command()
        def serve(self, config: _RegConfig):
            return config

    with pytest.raises(SystemExit) as exc:
        App().run(["migate"])  # typo
    assert exc.value.code == 64
    captured = capsys.readouterr()
    assert "myapp: unknown command: 'migate'" in captured.err
    assert "Did you mean:" in captured.err
    assert "migrate" in captured.err
    assert "Available commands:" in captured.err
    assert "serve" in captured.err


def test_command_app_name_collision_raises():
    with pytest.raises(CommandRegistrationError, match="collision"):

        class App(CommandApp):
            @command(name="reg")
            def reg(self, config: _RegConfig):
                return config

            @command(name="reg")
            def reg2(self, config: _RegConfig):
                return config


def test_command_app_alias_collision_raises():
    with pytest.raises(CommandRegistrationError, match="alias"):

        class App(CommandApp):
            @command(aliases=["x"])
            def reg(self, config: _RegConfig):
                return config

            @command(aliases=["x"])
            def crawl(self, config: _CrawlConfig):
                return config


def test_dispatch_command_override_for_async_or_wrappers():
    """Subclasses can wrap dispatch — a key extension point."""

    class App(CommandApp):
        wrapped: bool = False

        @command()
        def reg(self, config: _RegConfig):
            return config.target

        def dispatch_command(self, cmd, config):
            self.wrapped = True
            return super().dispatch_command(cmd, config)

    app = App()
    result = app.run(["reg", "--target", "x"])
    assert result == "x"
    assert app.wrapped is True


def test_build_sources_override_swaps_source_list():
    """Override the source-construction half of the CLI trio."""
    captured = {}

    class App(CommandApp):
        @command()
        def reg(self, config: _RegConfig):
            return config.target

        def build_sources(self, parsed, command):
            captured["called"] = True
            return super().build_sources(parsed, command)

    App().run(["reg", "--target", "x"])
    assert captured["called"] is True


def test_subclass_extends_parent_commands():
    class ParentApp(CommandApp):
        @command()
        def reg(self, config: _RegConfig):
            return ("parent.reg", config.target)

    class ChildApp(ParentApp):
        @command()
        def crawl(self, config: _CrawlConfig):
            return ("child.crawl", config.plugin)

    assert set(ChildApp._commands.keys()) == {"reg", "crawl"}
    app = ChildApp()
    assert app.run(["reg", "--target", "x"]) == ("parent.reg", "x")
    assert app.run(["crawl"]) == ("child.crawl", "all")


# ─────────────────────────────────────────────────────────────────────────────
# Exit code mapping
# ─────────────────────────────────────────────────────────────────────────────


_PROVIDED_A = ProvidedField(
    path="a",
    source_name="argparse",
    source_label="command line",
    value=1,
    source_native_key="--a",
    secret=False,
)
_PROVIDED_B = ProvidedField(
    path="b",
    source_name="env",
    source_label="environment",
    value=2,
    source_native_key="B",
    secret=False,
)


@pytest.mark.parametrize(
    ("exc", "expected_code"),
    [
        # 66 EX_NOINPUT
        (ConfigFileNotFoundError(Path("/missing.yaml")), 66),
        # 65 EX_DATAERR — YAML and value errors
        (YamlParseError(Path("/bad.yaml")), 65),
        (YamlSchemaError(Path("/bad.yaml"), reason="x"), 65),
        (YamlSizeLimitError(Path("/big.yaml"), size=1024, limit=10), 65),
        (SourceValueError("bad value"), 65),
        # 64 EX_USAGE — operator-side
        (
            MutexViolationError(
                group_name="g",
                field_paths=("a", "b"),
                provided=(_PROVIDED_A, _PROVIDED_B),
                required=False,
            ),
            64,
        ),
        (UnknownCommandError("nope", available=("ok",)), 64),
        (MissingRequiredError(()), 64),
        # 78 EX_CONFIG — framework-detected misconfig
        (EnvKeyCollisionError(key="K", field_a="a", field_b="b"), 78),
        (ConfigError("generic"), 78),
    ],
    ids=[
        "ConfigFileNotFoundError-66",
        "YamlParseError-65",
        "YamlSchemaError-65",
        "YamlSizeLimitError-65",
        "SourceValueError-65",
        "MutexViolationError-64",
        "UnknownCommandError-64",
        "MissingRequiredError-64",
        "EnvKeyCollisionError-78",
        "ConfigError-78",
    ],
)
def test_exit_code_per_error_class(exc, expected_code, capsys):
    """Each ConfigError subclass maps to a sysexits.h code; CommandApp
    propagates that code via sys.exit so k8s/systemd can distinguish
    user input (64-66) from framework misconfig (78)."""
    cmd = Command(name="reg", method_name="reg", config_class=_RegConfig)
    code = CommandApp()._render_config_error(exc, cmd=cmd, sources=[])
    assert code == expected_code


def test_discover_config_files_tags_cli_origin(tmp_path):
    """CLI `-c` paths carry origin='cli'. Diagnostics consume this
    tag — overrides may add `'discovered'`, `'xdg'`, etc."""
    from pathlib import Path

    cli_file = tmp_path / "from-cli.yaml"
    cli_file.write_text("target: c\n", encoding="utf-8")

    class App(CommandApp):
        @command()
        def reg(self, config: _RegConfig):
            return config.target

    parser = App()._build_cli_parser()
    parsed = parser.parse_args(["-c", str(cli_file), "reg"])
    discovered = App().discover_config_files(parsed)

    assert [(fo.path, fo.origin) for fo in discovered] == [
        (Path(str(cli_file)), "cli"),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Meta-flags
# ─────────────────────────────────────────────────────────────────────────────


def test_handle_meta_flags_can_be_overridden(capsys):
    """A subclass dropping a custom `--dry-run` flag short-circuits
    dispatch via the post-load hook."""

    class App(CommandApp):
        @command()
        def reg(self, config: _RegConfig):  # noqa: ARG002
            raise AssertionError("dispatch should not run when meta-flag short-circuits")

        def _handle_meta_flags(self, parsed, cmd, config, sources):
            short = super()._handle_meta_flags(parsed, cmd, config, sources)
            if short is not None:
                return short
            if getattr(parsed, "_dry_run", False):
                import sys

                sys.stdout.write(f"DRY RUN: {cmd.name}\n")
                return 7
            return None

        def _parse_cli(self, parser, argv):
            namespace = super()._parse_cli(parser, argv)
            namespace._dry_run = True
            return namespace

    rc = App().run(["reg"])
    assert rc == 7
    captured = capsys.readouterr()
    assert "DRY RUN: reg" in captured.out


# ─────────────────────────────────────────────────────────────────────────────
# CommandApp — config-class inference with multi-arg handlers
# ─────────────────────────────────────────────────────────────────────────────


def test_infer_config_class_finds_config_after_other_args():
    """Handlers like `def serve(self, session: Ctx, config: Cfg)` work
    without explicit `config_class=` — the inference walks all args
    and picks the first ConfigBase."""

    class _Cfg(ConfigBase):
        target: str = opt("x")

    class Ctx:  # noqa: D401 — stub for the test.
        pass

    class App(CommandApp):
        @command()
        def serve(self, session: Ctx, config: _Cfg):  # noqa: ARG002
            return config.target

        def dispatch_command(self, command, config):
            # Provide a Ctx for the handler — default dispatch only
            # passes config; override to thread the extra arg.
            handler = getattr(self, command.method_name)
            return handler(Ctx(), config)

    assert App().run(["serve"]) == "x"
