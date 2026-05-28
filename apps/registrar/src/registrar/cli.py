"""
`RegistrarApp` — the confline `CommandApp` that wires the entry point.

Each subcommand body lives in `registrar.commands.<name>`; this module
is the dispatch shim that confline's `@command` decorator binds to.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from confline import CommandApp, command
from registrar import list_spaces, list_storages
from registrar.config import ListSpacesConfig, ListStoragesConfig, RegisterConfig
from registrar.register.command import run as run_registration


class RegistrarApp(CommandApp):
    """Register Onedata datasets — confline-based entry point."""

    prog = "registrar"
    description = "Register dataset directories from a JSON/JSONL file into a single Onedata space."
    env_prefix = "REGISTRAR_"
    config_option = ("-c", "--config")

    @command()
    def register(self, config: RegisterConfig) -> int:
        """Plan, confirm, apply, and run registration of datasets into Onedata."""
        return run_registration(config)

    @command()
    def list_spaces(self, config: ListSpacesConfig) -> int:
        """List spaces on the configured Oneprovider."""
        return list_spaces.run(config)

    @command()
    def list_storages(self, config: ListStoragesConfig) -> int:
        """List storages on the configured Oneprovider."""
        return list_storages.run(config)


def main() -> int:
    """Console-script entry point — see `pyproject.toml` `[project.scripts]`."""
    return RegistrarApp().run()
