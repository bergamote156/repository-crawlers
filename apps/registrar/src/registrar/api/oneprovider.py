"""
Oneprovider API Client

Data operations on Oneprovider: file registration, lookups, shares.
"""

# pylint: disable=duplicate-code

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import json
from typing import Optional

import requests
import urllib3

from registrar import output

# Disable SSL warnings for development
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_TIMEOUT = 30  # seconds


class OneproviderClient:
    """
    Client for Oneprovider REST API.

    Handles data operations: file registration, lookups, shares.
    """

    def __init__(
        self,
        domain: str,
        token: str,
        verify_ssl: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """
        Initialize Oneprovider client.

        Args:
            domain: Oneprovider domain
            token: User token (space owner)
            verify_ssl: Whether to verify SSL certificates
            timeout: Request timeout in seconds
        """
        self.domain = domain
        self.token = token
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self._base_url = f"https://{domain}/api/v3/oneprovider"

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
                    f"Oneprovider API Error ({response.status_code}): "
                    f"{json.dumps(error_body, indent=2)}"
                )
            except json.JSONDecodeError:
                output.error(f"Oneprovider API Error ({response.status_code}): {response.text}")
            response.raise_for_status()

    # -------------------------------------------------------------------------
    # File operations
    # -------------------------------------------------------------------------

    def lookup_file_id(self, space_name: str, path: str) -> Optional[str]:
        """
        Lookup file ID by path in space.

        Args:
            space_name: Space name
            path: Path in space (without leading slash)

        Returns:
            File ID or None if not found
        """
        # Remove leading slash if present
        path = path.lstrip("/")

        url = f"{self._base_url}/lookup-file-id/{space_name}/{path}"

        response = requests.post(
            url=url,
            headers=self._headers(),
            verify=self.verify_ssl,
            timeout=self.timeout,
        )

        if response.ok and "fileId" in response.text:
            return response.json().get("fileId")

        return None

    def get_file_attrs(self, file_id: str) -> Optional[dict]:
        """
        Get file attributes including shares.

        Args:
            file_id: File ID

        Returns:
            File attributes dict or None if not found
        """
        url = f"{self._base_url}/data/{file_id}"

        response = requests.get(
            url=url,
            headers=self._headers(),
            verify=self.verify_ssl,
            timeout=self.timeout,
        )

        if response.ok:
            return response.json()

        return None

    def register_file(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        storage_id: str,
        space_id: str,
        file_url: str,
        dest_path: str,
        size: Optional[int] = None,
        auto_detect: bool = True,
    ) -> str:
        """
        Register a file in Onedata.

        Args:
            storage_id: Storage ID
            space_id: Space ID
            file_url: Remote file URL (used as storage_file_id for HTTP storage)
            dest_path: Destination path in space
            size: File size in bytes (optional if auto_detect=True)
            auto_detect: Auto-detect file attributes from storage

        Returns:
            File ID
        """
        url = f"{self._base_url}/data/register"
        payload = {
            "storageId": storage_id,
            "spaceId": space_id,
            "storageFileId": file_url,
            "destinationPath": dest_path,
            "autoDetectAttributes": auto_detect,
        }

        if not auto_detect and size is not None:
            payload["size"] = size

        response = requests.post(
            url=url,
            headers=self._headers_json(),
            json=payload,
            verify=self.verify_ssl,
            timeout=self.timeout,
        )
        self._handle_error(response)

        file_id = response.json().get("fileId")
        output.debug(f"Registered file: {dest_path} -> {file_id}")

        return file_id

    # -------------------------------------------------------------------------
    # Share operations
    # -------------------------------------------------------------------------

    def create_share(self, file_id: str, name: str, description: str = "") -> str:
        """
        Create a public share for a file or directory.

        Args:
            file_id: File or directory ID
            name: Share name
            description: Share description

        Returns:
            Share ID
        """
        url = f"{self._base_url}/shares"
        payload = {"fileId": file_id, "name": name, "description": description}

        response = requests.post(
            url=url,
            headers=self._headers_json(),
            json=payload,
            verify=self.verify_ssl,
            timeout=self.timeout,
        )
        self._handle_error(response)

        share_id = response.json().get("shareId")
        output.info(f"Created share '{name}' with ID: {share_id}")

        return share_id

    def get_share_details(self, share_id: str) -> Optional[dict]:
        """
        Get share details.

        Args:
            share_id: Share ID

        Returns:
            Share details dict or None if not found
        """
        url = f"{self._base_url}/shares/{share_id}"

        response = requests.get(
            url=url,
            headers=self._headers(),
            verify=self.verify_ssl,
            timeout=self.timeout,
        )

        if response.ok:
            return response.json()

        return None
