"""
Onezone API Client

User operations on Onezone: space creation, support tokens, handles.
"""

# pylint: disable=duplicate-code

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


class OnezoneClient:
    """
    Client for Onezone REST API.

    Handles user operations: space creation, support tokens, handle registration.
    """

    def __init__(
        self,
        domain: str,
        token: str,
        verify_ssl: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """
        Initialize Onezone client.

        Args:
            domain: Onezone domain
            token: User token (space owner)
            verify_ssl: Whether to verify SSL certificates
            timeout: Request timeout in seconds
        """
        self.domain = domain
        self.token = token
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self._base_url = f"https://{domain}/api/v3/onezone"

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
                    f"Onezone API Error ({response.status_code}): "
                    f"{json.dumps(error_body, indent=2)}"
                )
            except json.JSONDecodeError:
                output.error(f"Onezone API Error ({response.status_code}): {response.text}")
            response.raise_for_status()

    # -------------------------------------------------------------------------
    # Space operations
    # -------------------------------------------------------------------------

    def create_space(self, name: str) -> str:
        """
        Create a new space.

        Args:
            name: Space name

        Returns:
            Space ID
        """
        url = f"{self._base_url}/user/spaces"
        payload = {"name": name}

        response = requests.post(
            url=url,
            headers=self._headers_json(),
            json=payload,
            verify=self.verify_ssl,
            timeout=self.timeout,
        )
        self._handle_error(response)

        # Extract space ID from Location header
        location = response.headers.get("Location", "")
        space_id = location.split("/")[-1] if location else None

        if not space_id:
            # Fallback: try to get from response body
            space_id = response.json().get("spaceId")

        output.info(f"Created space '{name}' with ID: {space_id}")
        return space_id

    def create_support_token(self, space_id: str) -> str:
        """
        Create a support token for a space.

        Args:
            space_id: Space ID

        Returns:
            Support token
        """
        url = f"{self._base_url}/spaces/{space_id}/providers/token"

        response = requests.post(
            url=url,
            headers=self._headers_json(),
            json={},
            verify=self.verify_ssl,
            timeout=self.timeout,
        )
        self._handle_error(response)

        token = response.json().get("token")
        output.debug(f"Created support token for space {space_id}")

        return token

    # -------------------------------------------------------------------------
    # Handle operations
    # -------------------------------------------------------------------------

    def register_handle(
        self,
        handle_service_id: str,
        share_id: str,
        metadata_xml: str,
    ) -> str:
        """
        Register a handle for a share in the handle service.

        Args:
            handle_service_id: Handle service ID
            share_id: Share ID
            metadata_xml: Metadata in DataCite/OpenAIRE XML format

        Returns:
            Handle ID
        """
        url = f"{self._base_url}/user/handles"
        payload = {
            "handleServiceId": handle_service_id,
            "resourceType": "Share",
            "resourceId": share_id,
            "requestPublicHandle": False,
            "metadata": metadata_xml,
            "metadataPrefix": "oai_datacite",  ## TODO
        }

        response = requests.post(
            url=url,
            headers=self._headers_json(),
            json=payload,
            verify=self.verify_ssl,
            timeout=self.timeout,
        )
        self._handle_error(response)

        # Extract handle ID from Location header
        location = response.headers.get("Location", "")
        handle_id = location.split("/")[-1] if location else None

        if not handle_id:
            # Fallback: try to get from response body
            handle_id = response.json().get("handleId")

        output.info(f"Registered handle for share {share_id}: {handle_id}")

        return handle_id
