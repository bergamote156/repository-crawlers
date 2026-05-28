"""
Base exception type and exit-code convention for confline errors.

Each error class carries a `_EXIT_CODE: ClassVar[int]` so `CommandApp.run`
can map a typed error to a kernel-friendly exit code without a giant
isinstance ladder. Values come from `man sysexits` (BSD); k8s and
systemd restart policies key off them:

- `64` EX_USAGE — operator input error (mutex, unknown cmd, missing required)
- `65` EX_DATAERR — data is malformed (invalid value, broken YAML)
- `66` EX_NOINPUT — input file missing (config file not found)
- `78` EX_CONFIG — configuration error proper (env collision, unknown
  source, framework-detected misconfig)

When you add a new `ConfigError` subclass: pick the closest sysexits
code and set `_EXIT_CODE`. Default fallback is `78` — treat unknown
`ConfigError`s as configuration problems, not transient.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from typing import ClassVar


class ConfigError(Exception):
    """Base for all confline errors.

    Subclasses carry `_EXIT_CODE` so `CommandApp` can exit without an
    `isinstance` ladder. Rendering for CLI lives in
    `confline.ui.errors.render_for_cli` — a closed dispatch over
    confline's known error types.
    """

    _EXIT_CODE: ClassVar[int] = 78  # EX_CONFIG — sane default fallback.
