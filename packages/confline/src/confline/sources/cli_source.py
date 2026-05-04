"""
Command line interface source — reads from an already-parsed `argparse.Namespace`.

Markers exported here:
- `CliAlias("-c", "--config")` — override the auto-derived flag name(s)
- `CliPositional` — declare the field as a positional argument

To exclude a field from CLI resolution, pass `CliSource` itself to
`opt(excluded_from=[CliSource])`.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from argparse import Namespace
from collections.abc import Sequence
from typing import Any, ClassVar

from confline.config.base import is_list_of_config_base
from confline.config.schema import ConfigFieldInfo
from confline.sources.base import NO_VALUE, Source


class CliAlias:
    """Override the CLI flag name(s) for a field.

    Usage: `Annotated[str, CliAlias("-c", "--config")]`. Multiple same-type
    Annotated metadata follows last-wins per the discovery rules.

    NOTE: Hand-written rather than `@dataclass(frozen=True)`: the
    `*names` constructor matters more than the (modest) wins of
    dataclass-generated equality. `YamlPath` (also `*parts`) uses the
    same style; only single-field markers like `EnvAlias("LEGACY")`
    fit the frozen-dataclass shape naturally.
    """

    def __init__(self, *names: str) -> None:
        if not names:
            raise ValueError("CliAlias requires at least one name")
        self.names = tuple(names)

    def __repr__(self) -> str:
        return f"CliAlias{self.names!r}"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, CliAlias) and self.names == other.names

    def __hash__(self) -> int:
        return hash((type(self), self.names))


class CliPositional:
    """Annotated marker — declare the field as a positional CLI argument."""


class CliSource(Source):
    """Resolve fields from an `argparse.Namespace`.

    The parser builder emits arguments with `dest` set to the
    dotted `field.path` so a single namespace covers nested configs
    without name collisions. `vars(ns)` should contain only keys the
    user actually provided — the builder uses `default=argparse.SUPPRESS`
    for that.
    """

    name: ClassVar[str] = "argparse"
    display_label: ClassVar[str] = "command line"
    # Argparse aliases and the dotted flag are in the action invocation
    # header rendered by argparse itself — duplicating them as a
    # `argparse: --port` line under each option would be noise.
    display_in_help_block: ClassVar[bool] = False

    def __init__(self, namespace: Namespace) -> None:
        self._values = dict(vars(namespace))

    @classmethod
    def from_argv(
        cls,
        config_class: type,
        argv: "Sequence[str] | None" = None,
    ) -> "CliSource":
        """Build a parser for `config_class`, parse `argv`, return a `CliSource`.

        Convenience entry point — confline auto-derives the argparse
        parser from the config schema. For multi-command apps with
        subparsers, reach for `CommandApp` instead; it owns its own
        build-then-parse flow because it composes meta-flags.

        `argv=None` defaults to `sys.argv[1:]` (argparse's own default);
        pass an empty list to force "no flags provided".
        """
        # Lazy import: confline.sources lives below confline.ui in the
        # layer stack, so the parser builder can't be imported at module
        # load time without inducing a cycle.
        from confline.ui.argparse_builder import build_argparse_parser  # noqa: PLC0415

        parser = build_argparse_parser(config_class)
        return cls(parser.parse_args(argv))

    @classmethod
    def supports_field(cls, field: ConfigFieldInfo) -> bool:
        # `list[ConfigBase]` is list-of-dicts shape — argparse has no
        # flat-flag form for it. YAML carries this natively.
        return not is_list_of_config_base(field.field_type)

    def resolve(self, field: ConfigFieldInfo) -> Any:
        return self._values.get(".".join(field.path), NO_VALUE)

    def _describe_field(self, field: ConfigFieldInfo) -> str | None:
        if any(_is_positional(m) for m in field.annotated):
            # Positionals don't have a flag form; their label is the
            # last path segment as upper metavar (matches argparse
            # rendering in usage line).
            return field.path[-1].upper()

        for m in field.annotated:
            if isinstance(m, CliAlias):
                return m.names[0]

        # Mirror `argparse_builder._flag_names` so help/error fallbacks
        # match what argparse actually accepts (`--schema-dir`, not
        # `--schema_dir`).
        return "--" + ".".join(p.replace("_", "-") for p in field.path)

    def describe_unset_hint(self, key: str) -> str | None:
        if key.startswith("-"):
            return f" — remove {key}"
        return f" — remove the {key} argument"


def _is_positional(m: Any) -> bool:
    return m is CliPositional or (isinstance(m, type) and issubclass(m, CliPositional))
