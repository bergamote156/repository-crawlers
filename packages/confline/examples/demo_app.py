"""
Demo CommandApp — two subcommands, nested config, mutex group, YAML+env+CLI chain.

Use this as the reference for: subcommand dispatch (`@command`), nested
configs (`db.host`, `bind.port`), a mutually-exclusive group with a
soft `required=False`, source-side annotations (`EnvAlias`, `YamlPath`),
and provenance inspection via `config.source_of(...)`.

For the no-subcommand variant (single config, custom source order) see
`single_config_app.py` in this directory.

Run from `packages/confline/examples/` (any `python` in an env where
confline is importable):

    # Help — root and per-subcommand
    python demo_app.py --help
    python demo_app.py serve --help

    # Cross-source mutex (CLI port + env unix_socket — argparse alone wouldn't catch it)
    MYAPP_API_TOKEN=t MYAPP_BIND__UNIX_SOCKET=/tmp/x python demo_app.py serve --bind.port 9090

    # Coercion error from env (argparse would catch `--bind.port abc`; env path is post-parse)
    MYAPP_API_TOKEN=t MYAPP_BIND__PORT=abc python demo_app.py serve

    # Required field missing — `migrate` needs `--schema-dir` somewhere in the chain
    python demo_app.py migrate

    # Did-you-mean suggestion for an unknown subcommand
    python demo_app.py migate

NOTE: `MYAPP_API_TOKEN=t` shows up on every `serve` invocation because
`api_token` is declared without a default — confline treats it as
required. Drop the env var to see the `MissingRequiredError` rendering.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from pathlib import Path
from typing import Annotated, Literal

from confline import (
    CommandApp,
    ConfigBase,
    EnvAlias,
    MutuallyExclusiveGroup,
    YamlPath,
    command,
    opt,
)

# ─────────────────────────────────────────────────────────────────────────────
# Nested config — surfaces as `--db.host`, `MYAPP_DB__HOST`, `db.host` in YAML
# ─────────────────────────────────────────────────────────────────────────────


class DbConfig(ConfigBase):
    """Database connection settings."""

    host: str = opt("localhost", description="Database hostname.")
    port: int = opt(5432, description="Database TCP port.")
    name: str = opt("app", description="Database name.")
    password: str = opt(
        "changeme",
        description="Database password (read from env in production).",
        secret=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Mutex group — at most one of (port, unix_socket) may be user-provided
# ─────────────────────────────────────────────────────────────────────────────


class Bind(MutuallyExclusiveGroup, required=False):
    """How the server accepts connections — TCP or Unix socket."""

    port: int = opt(8080, description="TCP port to listen on.")
    unix_socket: Path | None = opt(
        None,
        description="Path to the Unix socket. Cannot combine with port.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Per-command config classes
# ─────────────────────────────────────────────────────────────────────────────


class ServeConfig(ConfigBase):
    """Configuration for the `serve` subcommand."""

    bind: Bind = opt(default_factory=Bind)
    db: DbConfig = opt(default_factory=DbConfig)

    log_level: Literal["debug", "info", "warning", "error"] = opt(
        "info", description="Verbosity of the request log.",
    )
    workers: int = opt(4, description="Number of worker processes.")
    verbose: int = opt(
        0,
        description="Increase log verbosity. Stack for more detail.",
        count=True,
    )
    mode: Literal["sync", "async"] = opt("sync", description="Request handling mode.")

    # `EnvAlias` overrides the default `MYAPP_API_TOKEN` env-var name
    # (which would already match here) — kept as a demo of how to pin
    # an env var when the auto-derived name doesn't match conventions.
    api_token: Annotated[str, EnvAlias("MYAPP_API_TOKEN")] = opt(
        description="Token clients send in the X-API-Token header.",
        secret=True,
    )
    extra_origins: list[str] = opt(
        default_factory=list,
        description="Additional CORS origins (repeatable: --extra-origins=...).",
    )


class MigrateConfig(ConfigBase):
    """Configuration for the `migrate` subcommand."""

    db: DbConfig = opt(default_factory=DbConfig)

    # `YamlPath` pins the YAML key to `schema_dir` even if the field is
    # later renamed — useful when the config file is shared with other
    # tools and the key name is part of the contract.
    schema_dir: Annotated[Path, YamlPath("schema_dir")] = opt(
        description="Directory containing migration files. Required.",
    )
    dry_run: bool = opt(False, description="Plan migrations without applying them.")


# ─────────────────────────────────────────────────────────────────────────────
# CommandApp wiring
# ─────────────────────────────────────────────────────────────────────────────


class MyApp(CommandApp):
    """Demo app with two commands and a YAML/env/CLI source chain."""

    prog = "myapp"
    description = "Demo application showcasing confline's UI surface."
    env_prefix = "MYAPP_"
    config_option = ("-c", "--config")

    @command()
    def serve(self, config: ServeConfig) -> int:
        # `config.source_of("db.host")` returns a `Provenance` so the
        # operator can confirm where each setting actually came from.
        # Useful for "why is workers=8 in prod?" debugging without
        # spelunking through env / yaml / flags by hand.
        port_origin = config.source_of("bind.port")
        print(
            f"[serve] starting on port={config.bind.port} "
            f"(from {port_origin.label}), db={config.db.host}",
        )
        return 0

    @command()
    def migrate(self, config: MigrateConfig) -> int:
        print(f"[migrate] dir={config.schema_dir}, dry_run={config.dry_run}")
        return 0


if __name__ == "__main__":
    raise SystemExit(MyApp().run())
