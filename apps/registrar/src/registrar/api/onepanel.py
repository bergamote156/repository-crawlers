"""
Onepanel REST client — admin operations: storage management, space support.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from typing import Final, NotRequired, TypedDict

import requests

from registrar import output
from registrar.api.utils import (
    DEFAULT_TIMEOUT,
    disable_ssl_warnings,
    handle_error,
    id_from_location,
    require_token,
)
from registrar.config import CommonConfig

disable_ssl_warnings()

SERVICE_NAME: Final[str] = "Onepanel"
DEFAULT_STORAGE_SUPPORT_SIZE: Final[int] = 1099511627776  # 1 TiB


class SpaceDetails(TypedDict):
    """Onepanel `GET /provider/spaces/{id}` payload (subset used by registrar)."""

    name: str
    storageId: str


class StorageDetails(TypedDict):
    """Onepanel `GET /provider/storages/{id}` payload (subset used by registrar).

    `endpoint` is the only optional field — only HTTP storages carry it.
    """

    name: str
    type: str
    readonly: bool
    importedStorage: bool
    endpoint: NotRequired[str]


def is_storage_compatible(storage: StorageDetails) -> bool:
    """True for HTTP readonly imported storages (the only kind registrar can use)."""
    return storage["type"] == "http" and storage["readonly"] and storage["importedStorage"]


class OnepanelClient:
    """Client for the Onepanel REST API."""

    def __init__(
        self,
        domain: str,
        token: str,
        port: int = 443,
        verify_ssl: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.domain = domain
        self.token = token
        self.port = port
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self._base_url = f"https://{domain}:{port}/api/v3/onepanel"

    @classmethod
    def from_config(cls, config: CommonConfig) -> "OnepanelClient":
        """Build an `OnepanelClient` from the resolved config.

        Requires `tokens.admin_token`; raises `MissingTokenError` otherwise.
        """
        return cls(
            domain=config.onedata.op_domain,
            token=require_token(config.tokens.admin_token, path="tokens.admin_token"),
            port=config.onedata.op_panel_port,
            verify_ssl=config.onedata.verify_ssl,
        )

    def _headers(self) -> dict:
        return {"X-Auth-Token": self.token}

    def _headers_json(self) -> dict:
        return {"X-Auth-Token": self.token, "Content-Type": "application/json"}

    # ─────────────────────────────────────────────────────────────────────────
    # Storage operations
    # ─────────────────────────────────────────────────────────────────────────

    def list_storages(self) -> list[str]:
        """Return all storage IDs known to the provider."""
        url = f"{self._base_url}/provider/storages"
        response = requests.get(
            url=url,
            headers=self._headers(),
            verify=self.verify_ssl,
            timeout=self.timeout,
        )
        handle_error(response, service=SERVICE_NAME)
        return response.json().get("ids", [])

    def get_storage_details(self, storage_id: str) -> StorageDetails:
        """Return the full configuration object for `storage_id`."""
        url = f"{self._base_url}/provider/storages/{storage_id}"
        response = requests.get(
            url=url,
            headers=self._headers(),
            verify=self.verify_ssl,
            timeout=self.timeout,
        )
        handle_error(response, service=SERVICE_NAME)
        return response.json()

    def add_storage(self, name: str, endpoint: str) -> str:
        """Create a new HTTP readonly imported storage and return its ID."""
        url = f"{self._base_url}/provider/storages"
        # The Onepanel API keys storage definitions by name in the request body.
        payload = {
            name: {
                "type": "http",
                "readonly": True,
                "importedStorage": True,
                "endpoint": endpoint,
            },
        }
        response = requests.post(
            url=url,
            headers=self._headers_json(),
            json=payload,
            verify=self.verify_ssl,
            timeout=self.timeout,
        )
        handle_error(response, service=SERVICE_NAME)

        storage_id = id_from_location(response)
        if not storage_id:
            storage_id = response.json().get(name, {}).get("id")

        output.info(f"Created storage '{name}' with ID: {storage_id}")
        return storage_id

    # ─────────────────────────────────────────────────────────────────────────
    # Space operations
    # ─────────────────────────────────────────────────────────────────────────

    def list_spaces(self) -> list[str]:
        """Return all space IDs supported by the provider."""
        url = f"{self._base_url}/provider/spaces"
        response = requests.get(
            url=url,
            headers=self._headers(),
            verify=self.verify_ssl,
            timeout=self.timeout,
        )
        handle_error(response, service=SERVICE_NAME)
        return response.json().get("ids", [])

    def get_space_details(self, space_id: str) -> SpaceDetails:
        """Return the full support details for `space_id`."""
        url = f"{self._base_url}/provider/spaces/{space_id}"
        response = requests.get(
            url=url,
            headers=self._headers(),
            verify=self.verify_ssl,
            timeout=self.timeout,
        )
        handle_error(response, service=SERVICE_NAME)
        return response.json()

    def support_space(
        self,
        storage_id: str,
        support_token: str,
        size: int = DEFAULT_STORAGE_SUPPORT_SIZE,
    ) -> str:
        """Support a space with `storage_id` in manual-import mode and return its ID."""
        url = f"{self._base_url}/provider/spaces"
        payload = {
            "token": support_token,
            "storageId": storage_id,
            "size": size,
            "storageImport": {"mode": "manual"},
        }
        response = requests.post(
            url=url,
            headers=self._headers_json(),
            json=payload,
            verify=self.verify_ssl,
            timeout=self.timeout,
        )
        handle_error(response, service=SERVICE_NAME)

        space_id = response.json().get("id")
        output.info(f"Supported space {space_id} with storage {storage_id}")
        return space_id
