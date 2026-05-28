"""
Single-config app — one mode, no subcommands, custom source order.

Use this as the reference for: programs with a single config object and
no subcommand dispatch, hand-assembled source chains where the canonical
`load_default` order doesn't fit, error rendering for operator-friendly
diagnostics, and provenance inspection.

For the multi-command variant see `demo_app.py` in this directory.

Source order chosen here: env → cli → yaml → default. This is the
"container-friendly" precedence — env vars set by the orchestrator
override anything baked into the launch script, CLI flags are for
ad-hoc overrides during shell-in debugging, the YAML file is the
reference shape, and declared defaults are the floor. Compare with
`load_default` (cli → env → yaml → default), where flags win.

Run from `packages/confline/examples/`:

    # Defaults — every value comes from `DefaultSource`
    python single_config_app.py

    # CLI override
    python single_config_app.py --port 9090

    # Env override beats CLI in this chain (note the reversed precedence)
    MYAPP_PORT=9090 python single_config_app.py --port 1234

    # YAML loaded automatically when ./config.yaml exists; env still beats it
    cp sample.yaml config.yaml && python single_config_app.py

    # Error rendering — bad value via env produces a SourceValueError
    MYAPP_PORT=abc python single_config_app.py
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import os
import sys
from pathlib import Path

from confline import (
    CliSource,
    ConfigBase,
    DefaultSource,
    EnvSource,
    YamlSource,
    load_or_exit,
    opt,
)


class AppConfig(ConfigBase):
    """One-shot service config — port, workers, debug flag."""

    port: int = opt(8080, description="HTTP port to bind.")
    workers: int = opt(4, description="Worker thread count.")
    debug: bool = opt(False, description="Enable debug logging.")


def main(argv: list[str]) -> int:
    yaml_path = Path("config.yaml")
    sources = [
        EnvSource(os.environ, prefix="MYAPP_"),
        CliSource.from_argv(AppConfig, argv),
        YamlSource.from_files([yaml_path]) if yaml_path.exists() else None,
        DefaultSource(),
    ]
    sources = [s for s in sources if s is not None]

    # `load_or_exit` resolves the config; on `ConfigError` it renders an
    # operator-friendly multi-line message to stderr and raises
    # SystemExit with the typed error's exit code (64 for usage, 65 for
    # bad data). For richer custom handling, catch `ConfigError`
    # yourself and call `render_for_cli` directly.
    config = load_or_exit(AppConfig, sources=sources, prog="myapp")

    print(f"port={config.port} (coming from {config.source_of('port').label})")
    print(f"workers={config.workers} (coming from {config.source_of('workers').label})")
    print(f"debug={config.debug} (coming from {config.source_of('debug').label})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
