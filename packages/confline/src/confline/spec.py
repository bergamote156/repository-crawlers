"""Neutral data types shared across confline's CLI subsystem."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from collections.abc import Mapping
from dataclasses import dataclass

from confline.config.base import ConfigBase


@dataclass(frozen=True)
class Command:
    """One registered command — name, the method that implements it,
    its config class, aliases, and a one-line description for `--help`."""

    name: str
    method_name: str
    config_class: type[ConfigBase]
    aliases: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class CliSpec:
    """What `build_command_app_parser` needs to render a CommandApp's CLI."""

    commands: Mapping[str, Command]
    config_option: tuple[str, ...] = ("-c", "--config")
    prog: str | None = None
    description: str | None = None
