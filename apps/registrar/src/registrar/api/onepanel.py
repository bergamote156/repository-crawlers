"""
Onepanel API Client

Admin operations on Oneprovider: storage management, space support.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import json

import requests
import urllib3

from registrar import output

# Disable SSL warnings for development
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_TIMEOUT = 30  # seconds


class OnepanelClient:
    """
    Client for Onepanel REST API.

    Handles admin operations: storage management, space support.
    """

    def __init__(
        self,
        domain: str,
        token: str,
        port: int = 443,
        verify_ssl: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """
        Initialize Onepanel client.

        Args:
            domain: Oneprovider domain
            token: Admin token
            port: Onepanel port (default: 443)
            verify_ssl: Whether to verify SSL certificates
            timeout: Request timeout in seconds
        """
        self.domain = domain
        self.token = token
        self.port = port
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self._base_url = f"https://{domain}:{port}/api/v3/onepanel"

    def _headers(self) -> dict:
        """Get default headers."""
        return {"X-Auth-Token": self.token}

    def _headers_json(self) -> dict:
        """Get headers for JSON requests."""
        return {"X-Auth-Token": self.token, "Content-Type": "application/json"}

    def _handle_error(self, response: requests.Response) -> None:
        """Log response body before raising error."""
        if not response.ok:
            try:
                error_body = response.json()
                output.error(
                    f"Onepanel API Error ({response.status_code}): "
                    f"{json.dumps(error_body, indent=2)}"
                )
            except json.JSONDecodeError:
                output.error(f"Onepanel API Error ({response.status_code}): {response.text}")
            response.raise_for_status()

    # -------------------------------------------------------------------------
    # Storage operations
    # -------------------------------------------------------------------------

    def list_storages(self) -> list[str]:
        """List all storage IDs."""
        url = f"{self._base_url}/provider/storages"
        response = requests.get(
            url=url,
            headers=self._headers(),
            verify=self.verify_ssl,
            timeout=self.timeout,
        )
        self._handle_error(response)
        return response.json().get("ids", [])

    def get_storage_details(self, storage_id: str) -> dict:
        """Get details of a specific storage."""
        url = f"{self._base_url}/provider/storages/{storage_id}"
        response = requests.get(
            url=url,
            headers=self._headers(),
            verify=self.verify_ssl,
            timeout=self.timeout,
        )
        self._handle_error(response)
        return response.json()

    def add_storage(self, name: str, endpoint: str) -> str:
        """
        Create a new HTTP readonly storage.

        Args:
            name: Storage name
            endpoint: HTTP endpoint URL (e.g., "https://example.com")

        Returns:
            Storage ID
        """
        url = f"{self._base_url}/provider/storages"
        payload = {
            name: {
                "type": "http",
                "readonly": True,
                "importedStorage": True,
                "endpoint": endpoint,
            }
        }

        response = requests.post(
            url=url,
            headers=self._headers_json(),
            json=payload,
            verify=self.verify_ssl,
            timeout=self.timeout,
        )
        self._handle_error(response)

        # Extract storage ID from Location header
        location = response.headers.get("Location", "")
        storage_id = location.split("/")[-1] if location else None

        if not storage_id:
            # Fallback: try to get from response body
            storage_id = response.json().get(name, {}).get("id")

        output.info(f"Created storage '{name}' with ID: {storage_id}")
        return storage_id

    # -------------------------------------------------------------------------
    # Space operations
    # -------------------------------------------------------------------------

    def list_spaces(self) -> list[str]:
        """List all space IDs supported by the provider."""
        url = f"{self._base_url}/provider/spaces"
        response = requests.get(
            url=url,
            headers=self._headers(),
            verify=self.verify_ssl,
            timeout=self.timeout,
        )
        self._handle_error(response)
        return response.json().get("ids", [])

    def get_space_details(self, space_id: str) -> dict:
        """Get details of a specific space."""
        url = f"{self._base_url}/provider/spaces/{space_id}"
        response = requests.get(
            url=url,
            headers=self._headers(),
            verify=self.verify_ssl,
            timeout=self.timeout,
        )
        self._handle_error(response)
        return response.json()

    def support_space(
        self,
        storage_id: str,
        support_token: str,
        size: int = 1099511627776,
    ) -> str:
        """
        Support a space with storage.

        Args:
            storage_id: Storage ID
            support_token: Space support token
            size: Support size in bytes (default: 1TB)

        Returns:
            Space ID
        """
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
        self._handle_error(response)

        space_id = response.json().get("id")
        output.info(f"Supported space {space_id} with storage {storage_id}")

        return space_id
