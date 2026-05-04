"""
confline — declarative configuration and subcommand framework for CLI tools.

The top-level surface covers what most apps need out of the box:

- Schema authoring: `ConfigBase`, `MutuallyExclusiveGroup`, `opt`,
  `field_validator`, `model_validator`.
- Resolution: `load_config`, `load_default`, `load_or_exit`.
- CommandApp orchestration: `CommandApp`, `command`.
- Built-in sources: `CliSource`, `EnvSource`, `YamlSource`, `DefaultSource`.
- Source-side annotations: `CliAlias`, `EnvAlias`, `YamlPath`.
- Errors users typically catch by type: `ConfigError` (umbrella),
  `MissingRequiredError`, `MutexViolationError`, `SourceValueError`,
  `ConfigFileNotFoundError`, `UnknownCommandError`.
- Provenance / introspection: `Provenance`, `SECRET_PLACEHOLDER`.
- Custom-source authoring: `Source`, `NO_VALUE`.

Niche extension points and framework internals stay in their submodules
and are imported directly by the few callers that need them. Examples:

    from confline.spec import Command            # CommandApp registry record
    from confline.errors import YamlParseError   # narrow yaml errors
    from confline.config import ConfigSchema     # schema introspection
    from confline.resolution.coerce import register_type  # type extension
    from confline.ui import build_argparse_parser  # internal UI machinery

Diagnostics:
    confline emits log records via the `"confline"` logger:

        import logging
        logging.getLogger("confline").setLevel(logging.DEBUG)

    DEBUG surfaces opt-in diagnostics: silent `except` sites in
    `describe_provenance` and other best-effort metadata calls log a
    single line per failure with full stack info, instead of going
    fully silent.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

# ─────────────────────────────────────────────────────────────────────────────
# Schema authoring
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# CommandApp orchestration
# ─────────────────────────────────────────────────────────────────────────────
from confline.commands import CommandApp, command
from confline.config import (
    SECRET_PLACEHOLDER,
    ConfigBase,
    MutuallyExclusiveGroup,
    Provenance,
    field_validator,
    model_validator,
    opt,
)

# ─────────────────────────────────────────────────────────────────────────────
# Errors users typically catch by type
# ─────────────────────────────────────────────────────────────────────────────
from confline.errors import (
    ConfigError,
    ConfigFileNotFoundError,
    MissingRequiredError,
    MutexViolationError,
    SourceValueError,
    UnknownCommandError,
)

# ─────────────────────────────────────────────────────────────────────────────
# Resolution / loading
# ─────────────────────────────────────────────────────────────────────────────
from confline.resolution.api import load_default, load_or_exit
from confline.resolution.resolver import load_config

# ─────────────────────────────────────────────────────────────────────────────
# Built-in sources + source-side annotations
# ─────────────────────────────────────────────────────────────────────────────
from confline.sources import (
    NO_VALUE,
    CliAlias,
    CliSource,
    DefaultSource,
    EnvAlias,
    EnvSource,
    Source,
    YamlPath,
    YamlSource,
)

__all__ = [
    "NO_VALUE",
    "SECRET_PLACEHOLDER",
    "CliAlias",
    "CliSource",
    "CommandApp",
    "ConfigBase",
    "ConfigError",
    "ConfigFileNotFoundError",
    "DefaultSource",
    "EnvAlias",
    "EnvSource",
    "MissingRequiredError",
    "MutexViolationError",
    "MutuallyExclusiveGroup",
    "Provenance",
    "Source",
    "SourceValueError",
    "UnknownCommandError",
    "YamlPath",
    "YamlSource",
    "command",
    "field_validator",
    "load_config",
    "load_default",
    "load_or_exit",
    "model_validator",
    "opt",
]
