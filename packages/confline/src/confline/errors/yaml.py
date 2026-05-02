"""
YAML-source errors.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

from confline.errors.base import ConfigError


class YamlPathCollisionError(ConfigError):
    """Two fields map to the same YAML path.

    - `path` — the derived YAML key path that collided.
    - `field_a`, `field_b` — dotted schema paths; kept so handlers and the
      fallback message can point the schema author at the two declarations.
    """

    def __init__(
        self,
        *,
        path: str,
        field_a: str,
        field_b: str,
    ) -> None:
        self.path = path
        self.field_a = field_a
        self.field_b = field_b

        super().__init__(
            f"yaml path collision: fields {field_a!r} and {field_b!r} both "
            f"map to {path!r}\n"
            f"\n"
            f"Resolve by:\n"
            f"  - change YamlPath(...) on one of the fields, or\n"
            f"  - rename one of the fields.",
        )


class ConfigFileNotFoundError(ConfigError):
    """A config file path declared explicitly does not exist on disk.

    - `path` — the missing file requested by the operator.
    - `suggestions` — nearby candidate paths for the compact message.

    Uses EX_NOINPUT so process supervisors can distinguish a missing input
    file from malformed configuration data.
    """

    _EXIT_CODE: ClassVar[int] = 66  # EX_NOINPUT

    def __init__(self, path: Path, *, suggestions: Sequence[str] = ()) -> None:
        self.path = path
        self.suggestions = tuple(suggestions)

        msg = f"config file not found: {path}"
        if suggestions:
            msg += f" (did you mean: {', '.join(suggestions)})"

        super().__init__(msg)


class YamlParseError(ConfigError):
    """`yaml.safe_load` raised while parsing a config file.

    - `path` — the file that failed to parse.
    - `line`, `column` — best-effort location from the YAML parser.
    - `detail` — the parser's short reason; preserved without exposing the
      full exception object.
    """

    _EXIT_CODE: ClassVar[int] = 65  # EX_DATAERR

    def __init__(
        self,
        path: Path,
        *,
        line: int | None = None,
        column: int | None = None,
        detail: str = "",
    ) -> None:
        self.path = path
        self.line = line
        self.column = column
        self.detail = detail

        loc = ""
        if line is not None:
            loc = f":{line}"
            if column is not None:
                loc += f":{column}"

        suffix = f" — {detail}" if detail else ""
        super().__init__(f"YAML parse error in {path}{loc}{suffix}")


class YamlSchemaError(ConfigError):
    """A YAML file parsed cleanly but its top-level shape is unusable.

    - `path` — the file with the bad shape.
    - `reason` — description of the unsupported shape (e.g. empty document
      or non-mapping top level).
    """

    _EXIT_CODE: ClassVar[int] = 65  # EX_DATAERR

    def __init__(self, path: Path, *, reason: str) -> None:
        self.path = path
        self.reason = reason

        super().__init__(f"YAML schema error in {path}: {reason}")


class YamlSizeLimitError(ConfigError):
    """Config file exceeds `YamlSource.MAX_FILE_BYTES`.

    - `path` — the oversized file.
    - `size` — actual byte count.
    - `limit` — the configured maximum.
    """

    _EXIT_CODE: ClassVar[int] = 65  # EX_DATAERR

    def __init__(self, path: Path, *, size: int, limit: int) -> None:
        self.path = path
        self.size = size
        self.limit = limit

        super().__init__(
            f"YAML file too large: {path} is {size} bytes (limit {limit})",
        )
