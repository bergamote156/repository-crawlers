"""Shared helpers for the Onedata REST clients in this package."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import json
import logging
from typing import Final

import requests
import urllib3

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT: Final[int] = 30

ENV_PREFIX: Final[str] = "REGISTRAR_"
"""Mirror of `RegistrarApp.env_prefix` — used to render unset-config hints.

Kept here so `api/` does not have to import the CLI module just to
reach for the same string. Update both together if the prefix changes.
"""


def disable_ssl_warnings() -> None:
    """Suppress `InsecureRequestWarning` for self-signed dev/test deployments.

    The `verify_ssl` flag is honoured per-request; this only quiets the
    noisy warnings when the user opted out globally.
    """
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def id_from_location(response: requests.Response) -> str | None:
    """Extract the trailing path segment of the `Location` header, if any."""
    location = response.headers.get("Location", "")
    return location.rsplit("/", 1)[-1] if location else None


def handle_error(response: requests.Response, *, service: str) -> None:
    """Log the response body before letting `raise_for_status` fire.

    `service` is the human-readable client label used in the log line —
    `Onezone`, `Oneprovider`, `Onepanel`. No-op on `2xx`.
    """
    if response.ok:
        return

    try:
        error_body = response.json()
        logger.error(
            "%s API Error (%d): %s",
            service,
            response.status_code,
            json.dumps(error_body, indent=2),
        )
    except json.JSONDecodeError:
        logger.error("%s API Error (%d): %s", service, response.status_code, response.text)

    response.raise_for_status()


def env_var_for(path: str) -> str:
    """Derive the env var confline maps to a dotted config path.

    Example: `"tokens.admin_token"` → `"REGISTRAR_TOKENS__ADMIN_TOKEN"`.
    Mirrors confline's default `prefix + "__".join(p.upper() for p in path)`
    convention; honour `EnvAlias` overrides at the call site if any field
    ever opts out.
    """
    return ENV_PREFIX + "__".join(p.upper() for p in path.split("."))


class MissingTokenError(RuntimeError):
    """Raised when a required token is empty.

    Carries the dotted config path so the CLI can render a hint without
    re-deriving the env var name. The path doubles as the human-readable
    field label (it's the same string a user puts in YAML).
    """

    def __init__(self, path: str) -> None:
        env_var = env_var_for(path)
        super().__init__(
            f"{path} is not set — provide it via {env_var}, YAML config, or the matching CLI flag.",
        )
        self.path = path
        self.env_var = env_var


def require_token(value: str, *, path: str) -> str:
    """Return `value` or raise `MissingTokenError(path)` when empty."""
    if not value:
        raise MissingTokenError(path)

    return value
