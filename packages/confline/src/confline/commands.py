"""
CommandApp orchestrator + `@command` decorator.

Top of confline's dependency stack — the orchestrator that wires
parser building, argv parsing, source construction, config
resolution, and command dispatch into a single `run()` method.

Users subclass `CommandApp`, decorate methods with `@command`, and
call `run(argv)`. The class exposes documented override seams; see
`CommandApp.__doc__` for the contract.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import difflib
import inspect
import logging
import os
import sys
import typing
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, ClassVar

from rich.console import Console

from confline.config.base import ConfigBase, is_config_class
from confline.errors import (
    CommandRegistrationError,
    ConfigError,
    UnknownCommandError,
)
from confline.resolution.resolver import load_config
from confline.sources import (
    CliSource,
    DefaultSource,
    EnvSource,
    Source,
    YamlSource,
)
from confline.sources.base import FileOrigin
from confline.spec import CliSpec, Command
from confline.ui.argparse_builder import build_command_app_parser
from confline.ui.errors import render_for_cli

logger = logging.getLogger("confline")

_COMMAND_FLAG = "__confline_command__"


# ─────────────────────────────────────────────────────────────────────────────
# Command decorator
# ─────────────────────────────────────────────────────────────────────────────


def command(
    fn: Callable[..., Any] | None = None,
    /,
    *,
    name: str | None = None,
    config_class: type[ConfigBase] | None = None,
    aliases: Sequence[str] = (),
    description: str | None = None,
) -> Any:
    """Mark a method as a command handler.

    Two call forms are accepted:

    - bare `@command` (no parens) — name and config_class are inferred
    - `@command(name=..., config_class=..., ...)` — explicit overrides

    Default name is the method's `__name__` with `_` replaced by `-`
    (so `def list_orgs(...)` → `list-orgs`); this matches Click and
    Typer conventions for kebab-case CLIs. Pass `name="snake_form"`
    to keep underscores.

    `config_class` is inferred from the first `ConfigBase`-annotated
    argument if not given explicitly. Aliases are wired into the
    argparse subparser.

    `description` is the one-liner shown in top-level `--help`. When
    omitted, the first non-blank line of the method's docstring is
    used — keeps the source of truth on the handler itself:

        @command
        def serve(self, config: ServeConfig):
            \"\"\"Start the HTTP server.\"\"\"
            ...
    """
    if fn is not None:
        # @command (bare) — `fn` is the decorated method
        return _attach_command_meta(
            fn,
            name=name,
            config_class=config_class,
            aliases=aliases,
            description=description,
        )

    # @command(...) form — return a decorator
    def decorator(inner: Callable[..., Any]) -> Callable[..., Any]:
        return _attach_command_meta(
            inner,
            name=name,
            config_class=config_class,
            aliases=aliases,
            description=description,
        )

    return decorator


def _attach_command_meta(
    fn: Callable[..., Any],
    *,
    name: str | None,
    config_class: type[ConfigBase] | None,
    aliases: Sequence[str],
    description: str | None,
) -> Callable[..., Any]:
    cls = config_class or _infer_config_class(fn)
    if cls is None:
        raise CommandRegistrationError(
            f"@command on {fn.__name__}: cannot infer config_class. "
            "Annotate the config argument or pass config_class= explicitly.",
        )

    meta = {
        "name": name if name is not None else fn.__name__.replace("_", "-"),
        "config_class": cls,
        "aliases": tuple(aliases),
        "description": description if description is not None else _first_doc_line(fn),
    }
    setattr(fn, _COMMAND_FLAG, meta)
    return fn


def _first_doc_line(fn: Callable[..., Any]) -> str:
    """Return the first non-blank line of `fn.__doc__`, stripped.

    Used as the auto-derived `Command.description` when the
    `@command` decorator does not pass one explicitly.
    """
    doc = inspect.getdoc(fn) or ""
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _infer_config_class(fn: Callable[..., Any]) -> type[ConfigBase] | None:
    """Return the first `ConfigBase` subclass found among the handler's args.

    Iterates *all* parameters (skipping `self`/`cls`) and picks the
    first one annotated as a `ConfigBase` subclass. This lets handlers
    take extra positional args before the config: a common pattern is
    `def serve(self, session: SessionCtx, config: ServeConfig)` where
    the framework still needs to find `ServeConfig`.
    """
    try:
        hints = typing.get_type_hints(fn)
    except Exception:  # noqa: BLE001
        # Forward refs from `from __future__ import annotations` may
        # not resolve at decoration time; the user can still pass
        # config_class= explicitly.
        return None

    sig = inspect.signature(fn)
    for param_name in sig.parameters:
        if param_name in ("self", "cls"):
            continue
        annot = hints.get(param_name)
        if is_config_class(annot):
            return annot
    return None


# ─────────────────────────────────────────────────────────────────────────────
# CommandApp
# ─────────────────────────────────────────────────────────────────────────────


class CommandApp:
    """Sync orchestrator for a CLI tool. Default backend: argparse.

    Subclass `CommandApp`, decorate methods with `@command`, and
    instantiate. Bare `myapp` prints top-level help and returns 0;
    `myapp <cmd> [flags...]` resolves a config and dispatches.

    Override seams (in order of how often you'll touch them):

    - `env_prefix` / `config_option` / `prog` / `description` —
      class-level knobs for naming and CLI shape.
    - `dispatch_command(cmd, config)` — wrap invocation for async,
      context managers, instrumentation. The default is sync method
      call (see method docstring for an `asyncio` example).
    - `_handle_meta_flags(parsed, cmd, config, sources)` — post-load
      hook for `--dry-run`, `--validate-only`, etc. Return an int to
      short-circuit dispatch with that exit code.
    - `build_sources(parsed, cmd)` — replace or extend the default
      argparse → env → yaml → defaults stack.
    - `discover_config_files(parsed)` — replace path discovery for
      XDG/HOME walk-up or other strategies.
    - `_build_cli_parser` / `_parse_cli` — swap the entire CLI
      library (drop argparse for click, etc.).
    """

    # --- Override knobs ---

    env_prefix: ClassVar[str] = ""
    """Prefix for `EnvSource`; e.g. `"MYAPP_"` reads `MYAPP_TARGET=...`."""

    config_option: ClassVar[tuple[str, ...]] = ("-c", "--config")
    """CLI flag(s) for the YAML config-file argument. Set to `()` to disable."""

    prog: ClassVar[str | None] = None
    """Program name shown in `--help` and error output. Falls back to `argv[0]`."""

    description: ClassVar[str | None] = None
    """One-line description shown in top-level `--help`."""

    # Populated by __init_subclass__.
    _commands: ClassVar[dict[str, Command]] = {}
    _command_aliases: ClassVar[dict[str, Command]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._commands, cls._command_aliases = _collect_commands(cls)

    # --- Run pipeline ---

    def run(self, argv: Sequence[str] | None = None) -> Any:
        """Build the parser, parse argv, dispatch the matching command.

        Phases (each pulled out as an override seam):

        - `_prepare` — parse argv into `(namespace, command, sources)`.
          Returns `None` for bare `myapp` (top-level help printed,
          caller exits 0).
        - `_load` — run `load_config` with typed-error rendering wired
          to `sys.exit` so `ConfigError` subclasses surface their
          sysexits-keyed exit code (64/65/66 for operator typos, 78
          for framework-detected misconfig).
        - `_handle_meta_flags` — post-load hook for `--dry-run` etc.;
          return int to short-circuit dispatch.
        - `dispatch_command` — invoke the handler.

        Unknown commands surface as `UnknownCommandError` from the
        parser with did-you-mean suggestions (rendered to stderr,
        exits 64).
        """
        try:
            prep = self._prepare(argv)
        except UnknownCommandError as exc:
            exit_code = self._render_config_error(exc, cmd=None, sources=())
            sys.exit(exit_code)

        if prep is None:
            return 0

        parsed, cmd, sources = prep
        config = self._load(cmd, sources)
        short = self._handle_meta_flags(parsed, cmd, config, sources)
        if short is not None:
            return short

        return self.dispatch_command(cmd, config)

    def _prepare(
        self,
        argv: Sequence[str] | None,
    ) -> "tuple[Any, Command, list[Source]] | None":
        """Build parser → parse argv → look up command → build sources.

        Returns `(parsed_namespace, command, sources)` on a normal
        invocation. Returns `None` when the user typed `myapp` with
        no subcommand — top-level help has already been printed and
        the caller should return exit 0.
        """
        parser = self._build_cli_parser()
        parsed = self._parse_cli(parser, argv)
        if getattr(parsed, "_command", None) is None:
            parser.print_help()
            return None

        cmd = self._lookup_command(parsed)
        sources = self.build_sources(parsed, cmd)
        return parsed, cmd, sources

    def _load(
        self,
        cmd: Command,
        sources: Sequence[Source],
    ) -> ConfigBase:
        """Run `load_config`; render typed errors to stderr on failure.

        On `ConfigError` the formatted message goes to stderr and
        `sys.exit` fires with the class's `_EXIT_CODE`.
        """
        try:
            return load_config(cmd.config_class, sources=sources)
        except ConfigError as exc:
            exit_code = self._render_config_error(exc, cmd=cmd, sources=sources)
            sys.exit(exit_code)

    def _handle_meta_flags(
        self,
        parsed: Any,  # noqa: ARG002
        cmd: Command,  # noqa: ARG002
        config: ConfigBase,  # noqa: ARG002
        sources: Sequence[Source],  # noqa: ARG002
    ) -> int | None:
        """Post-load, pre-dispatch hook for side-effecting flags.

        Return a non-None integer to short-circuit `run()` with that
        exit code (and skip `dispatch_command`); return `None` to
        fall through to the command handler.

        Subclasses adding their own (`--dry-run`, `--validate-only`,
        ...) should chain `super` first and only act when the parent
        returned `None`:

            def _handle_meta_flags(self, parsed, cmd, config, sources):
                short = super()._handle_meta_flags(parsed, cmd, config, sources)
                if short is not None:
                    return short
                if getattr(parsed, "_dry_run", False):
                    ...
                    return 0
                return None
        """
        return None

    # --- Source construction ---

    def build_sources(self, parsed: Any, command: Command) -> list[Source]:  # noqa: ARG002
        """Default source list: argparse → env → yaml (if -c) → defaults.

        Override to add custom sources, change the order, or filter
        based on the active command.
        """
        sources: list[Source] = [
            CliSource(parsed),
            EnvSource(os.environ, prefix=self.env_prefix),
        ]

        config_files = self.discover_config_files(parsed)
        if config_files:
            sources.append(YamlSource.from_files(config_files))

        sources.append(DefaultSource())
        return sources

    def discover_config_files(self, parsed: Any) -> list[FileOrigin]:
        """Return CLI `-c` paths tagged with `origin="cli"`.

        Override to add XDG/HOME walk-up, secret-mount discovery,
        etc. Origin labels (`"discovered"`, `"xdg"`, ...) are
        free-form and surface in operator-facing diagnostics.
        """
        return [
            FileOrigin(path=p, origin="cli") for p in getattr(parsed, "_config_files", None) or []
        ]

    def _label_sources(self) -> list[Source]:
        """Sources used solely for `--help` rendering (env name, yaml
        path, etc.). Mirrors `build_sources` structurally, but
        constructed without runtime values so `describe_field` is
        the only meaningful method called on them.

        Subclass override goes here when `build_sources` is itself
        overridden — keep the two consistent so help and runtime
        agree on what each field is named via.
        """
        # local import: argparse is implementation-detail of the
        # default backend, not a contract of CommandApp.
        from argparse import Namespace  # noqa: PLC0415

        return [
            CliSource(Namespace()),
            EnvSource({}, prefix=self.env_prefix),
            YamlSource(scopes=()),
            DefaultSource(),
        ]

    # --- CLI parser (override seam) ---

    def _build_cli_parser(self) -> Any:
        return build_command_app_parser(
            spec=self._cli_spec(),
            label_sources=self._label_sources(),
        )

    def _cli_spec(self) -> CliSpec:
        """Build the `CliSpec` that `_build_cli_parser` hands to the builder.

        Subclass override goes here if the spec needs runtime tweaks
        (e.g. filtering `_commands` based on environment).
        """
        return CliSpec(
            commands=self._commands,
            config_option=self.config_option,
            prog=self.prog or _derive_prog(),
            description=self.description,
        )

    def _parse_cli(self, parser: Any, argv: Sequence[str] | None) -> Any:
        return parser.parse_args(argv)

    # --- Dispatch ---

    def dispatch_command(self, command: Command, config: ConfigBase) -> Any:
        """Default is sync method invocation. Override for async / context managers.

        Async example — run async handlers via `asyncio.run`:

            import asyncio, inspect

            class App(CommandApp):
                def dispatch_command(self, command, config):
                    handler = getattr(self, command.method_name)
                    result = handler(config)
                    if inspect.iscoroutine(result):
                        return asyncio.run(result)
                    return result

        Context-manager example — open a session that wraps every
        command:

            class App(CommandApp):
                def dispatch_command(self, command, config):
                    with open_session(config) as session:
                        handler = getattr(self, command.method_name)
                        return handler(session, config)
        """
        handler = getattr(self, command.method_name)
        return handler(config)

    # --- Error & lookup ---

    def _lookup_command(self, parsed: Any) -> Command:
        name = getattr(parsed, "_command", None)
        if name in self._commands:
            return self._commands[name]
        if name in self._command_aliases:
            return self._command_aliases[name]

        available = sorted(self._commands.keys())
        suggestions: list[str] = []
        if name is not None:
            suggestions = difflib.get_close_matches(name, available, n=3, cutoff=0.6)

        raise UnknownCommandError(
            name,
            available=available,
            suggestions=suggestions,
        )

    def _render_config_error(
        self,
        exc: ConfigError,
        *,
        cmd: Command | None,
        sources: Sequence[Source],
    ) -> int:
        """Write a formatted error message to stderr; return the exit code.

        `render_for_cli` is a closed dispatch over confline's known
        error types — single seam regardless of how many subclasses
        exist. Exit code comes from `_EXIT_CODE` (sysexits.h).
        """
        prog = self.prog or _derive_prog()
        command_name = cmd.name if cmd is not None else None
        rendered = render_for_cli(
            exc,
            prog=prog,
            command=command_name,
            label_sources=sources,
        )
        # `Console(file=stderr)` auto-detects tty and `NO_COLOR`, so we
        # don't need to branch on environment ourselves. `highlight=False`
        # keeps rich from re-styling pre-styled `Text` fragments.
        Console(file=sys.stderr, highlight=False).print(rendered)
        return type(exc)._EXIT_CODE


def _derive_prog() -> str | None:
    """Best-effort `prog` for error formatting when `CommandApp.prog` is None."""
    return Path(sys.argv[0]).name if sys.argv else None


# ─────────────────────────────────────────────────────────────────────────────
# Command collection from MRO
# ─────────────────────────────────────────────────────────────────────────────


def _collect_commands(
    cls: type,
) -> tuple[dict[str, Command], dict[str, Command]]:
    """Walk the MRO base-to-derived, build the canonical command tables."""
    by_method: dict[str, Command] = {}
    method_order: list[str] = []

    for klass in reversed(cls.__mro__):
        if klass is object:
            continue
        for method_name, attr in vars(klass).items():
            meta = getattr(attr, _COMMAND_FLAG, None)
            if meta is None:
                continue
            if method_name not in by_method:
                method_order.append(method_name)
            by_method[method_name] = Command(
                name=meta["name"],
                method_name=method_name,
                config_class=meta["config_class"],
                aliases=meta["aliases"],
                description=meta["description"],
            )

    commands: dict[str, Command] = {}
    aliases: dict[str, Command] = {}
    for method_name in method_order:
        cmd = by_method[method_name]
        if cmd.name in commands or cmd.name in aliases:
            raise CommandRegistrationError(
                f"command name collision: {cmd.name!r} already registered",
            )
        commands[cmd.name] = cmd
        for alias in cmd.aliases:
            if alias in commands or alias in aliases:
                raise CommandRegistrationError(
                    f"alias collision: {alias!r} already registered",
                )
            aliases[alias] = cmd

    return commands, aliases
