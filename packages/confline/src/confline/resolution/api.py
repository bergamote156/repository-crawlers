"""
High-level entry points that compose Sources + Resolution + UI.

`load_default` covers the canonical single-config / single-command
case. `load_or_exit` wraps `load_config` with operator-friendly error
rendering — the same path `CommandApp` takes on a `ConfigError` —
so non-CommandApp programs skip the try/except boilerplate.

Lives above the resolver in the layer stack so it can freely import
both `confline.sources` and `confline.ui.errors` at module top — the
resolver itself stays unaware of UI.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import os
import sys
from collections.abc import Sequence
from pathlib import Path

from rich.console import Console

from confline.config.base import ConfigBase
from confline.errors import ConfigError
from confline.resolution.resolver import load_config
from confline.sources.base import Source
from confline.sources.cli_source import CliSource
from confline.sources.default_source import DefaultSource
from confline.sources.env_source import EnvSource
from confline.sources.yaml_source import YamlSource
from confline.ui.errors import render_for_cli


def load_default(
    config_class: type[ConfigBase],
    *,
    env_prefix: str = "",
    yaml_files: Sequence[Path] = (),
    argv: Sequence[str] | None = None,
) -> ConfigBase:
    """One-shot load using the canonical chain (cli → env → yaml → default).

    `argv=None` skips CLI parsing entirely (suited to long-lived
    services that don't accept flags). Pass any sequence — even `[]`
    — to enable CLI parsing via `CliSource.from_argv`; argparse sees
    the empty argv as "no flags provided", which is different from
    "no CLI source at all".

    For multi-command apps reach for `CommandApp` instead — this
    shortcut covers the single-config / single-command case.
    """
    sources: list[Source] = []
    if argv is not None:
        sources.append(CliSource.from_argv(config_class, argv))

    sources.append(EnvSource(os.environ, prefix=env_prefix))

    if yaml_files:
        sources.append(YamlSource.from_files(list(yaml_files)))

    sources.append(DefaultSource())

    return load_config(config_class, sources=sources)


def load_or_exit(
    config_class: type[ConfigBase],
    *,
    sources: Sequence[Source],
    prog: str | None = None,
) -> ConfigBase:
    """Resolve `config_class`; on `ConfigError` render to stderr and `SystemExit`.

    Same error path `CommandApp` takes on a typed framework failure —
    operator-friendly multi-line stderr (field path, given value,
    source, expected type, 'Try one of' hints) plus a `SystemExit`
    carrying the error's `_EXIT_CODE` (64 EX_USAGE for missing fields
    / mutex violations, 65 EX_DATAERR for invalid values).

    Use from a `main()` to skip the try/except + render_for_cli +
    sys.exit boilerplate; for richer custom handling, catch
    `ConfigError` yourself and call `render_for_cli` directly.
    """
    try:
        return load_config(config_class, sources=sources)
    except ConfigError as exc:
        rendered = render_for_cli(exc, prog=prog, label_sources=sources)
        Console(file=sys.stderr, highlight=False).print(rendered)
        raise SystemExit(getattr(exc, "_EXIT_CODE", 1)) from exc
