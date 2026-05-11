"""
Onezone REST client — user-level operations: spaces, support tokens, handles.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import logging
from typing import Final

import requests

from registrar.api.utils import (
    DEFAULT_TIMEOUT,
    disable_ssl_warnings,
    handle_error,
    id_from_location,
    require_token,
)
from registrar.config import CommonConfig

logger = logging.getLogger(__name__)

disable_ssl_warnings()

SERVICE_NAME: Final[str] = "Onezone"


class OnezoneClient:
    """Client for the Onezone REST API."""

    def __init__(
        self,
        domain: str,
        token: str,
        verify_ssl: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.domain = domain
        self.token = token
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self._base_url = f"https://{domain}/api/v3/onezone"

    @classmethod
    def from_config(cls, config: CommonConfig) -> "OnezoneClient":
        """Build an `OnezoneClient` from the resolved config.

        Requires `tokens.space_owner_token`; raises `MissingTokenError` otherwise.
        """
        return cls(
            domain=config.onedata.oz_domain,
            token=require_token(
                config.tokens.space_owner_token,
                path="tokens.space_owner_token",
            ),
            verify_ssl=config.onedata.verify_ssl,
        )

    def _headers(self) -> dict:
        return {"X-Auth-Token": self.token}

    def _headers_json(self) -> dict:
        return {"X-Auth-Token": self.token, "Content-Type": "application/json"}

    # ─────────────────────────────────────────────────────────────────────────
    # Space operations
    # ─────────────────────────────────────────────────────────────────────────

    def create_space(self, name: str) -> str:
        """Create a new space and return its ID."""
        url = f"{self._base_url}/user/spaces"
        response = requests.post(
            url=url,
            headers=self._headers_json(),
            json={"name": name},
            verify=self.verify_ssl,
            timeout=self.timeout,
        )
        handle_error(response, service=SERVICE_NAME)

        space_id = id_from_location(response) or response.json().get("spaceId")
        logger.info("Created space '%s' with ID: %s", name, space_id)
        return space_id

    def create_support_token(self, space_id: str) -> str:
        """Mint a support token to be redeemed by an Oneprovider."""
        url = f"{self._base_url}/spaces/{space_id}/providers/token"
        response = requests.post(
            url=url,
            headers=self._headers_json(),
            json={},
            verify=self.verify_ssl,
            timeout=self.timeout,
        )
        handle_error(response, service=SERVICE_NAME)

        token = response.json().get("token")
        logger.debug("Created support token for space %s", space_id)
        return token

    # ─────────────────────────────────────────────────────────────────────────
    # Handle operations
    # ─────────────────────────────────────────────────────────────────────────

    def register_handle(
        self,
        *,
        handle_service_id: str,
        share_id: str,
        metadata_xml: str,
        metadata_prefix: str = "oai_datacite",
        pid_to_reuse: str | None = None,
    ) -> str:
        """Attach a public handle to a share and return the new handle ID.

        With `pid_to_reuse=None` Onezone asks the handle service to mint a
        fresh public handle. When a PID is supplied, Onezone records it
        against the share without minting a new one — the way to attach an
        externally-issued handle to an existing share.

        Both modes use a single non-public toggle on the same endpoint
        (`requestPublicHandle` / `publicHandleToReuse`).
        """
        # Supported metadata prefixes on the server: oai_dc, oai_datacite,
        # oai_openaire, edm. metadata_prefix is plumbed through but defaulted
        # because dataset records do not yet carry their schema.
        payload: dict[str, object] = {
            "handleServiceId": handle_service_id,
            "resourceType": "Share",
            "resourceId": share_id,
            "metadata": metadata_xml,
            "metadataPrefix": metadata_prefix,
        }
        if pid_to_reuse is None:
            payload["requestPublicHandle"] = True
        else:
            payload["requestPublicHandle"] = False
            payload["publicHandleToReuse"] = pid_to_reuse

        url = f"{self._base_url}/user/handles"
        response = requests.post(
            url=url,
            headers=self._headers_json(),
            json=payload,
            verify=self.verify_ssl,
            timeout=self.timeout,
        )
        handle_error(response, service=SERVICE_NAME)

        handle_id = id_from_location(response) or response.json().get("handleId")
        logger.info("Registered handle for share %s: %s", share_id, handle_id)
        return handle_id
