"""
eCUDO API HTTP Client

Low-level HTTP client for eCUDO API. Handles only HTTP concerns:
- Session management
- Retries with exponential backoff
- JSON fetching
"""

import asyncio
from typing import Optional

import aiohttp  # type: ignore[import-not-found]

from ecudo import output


class EcudoClient:
    """
    Low-level HTTP client for eCUDO API.

    Usage:
        async with EcudoClient() as client:
            orgs = await client.get_organizations()
            metadata = await client.get_record_metadata(record_id)
    """

    def __init__(
        self,
        base_url: str = "http://central.ecudo.pl",
        timeout: int = 15,
        max_retries: int = 3,
    ):
        """
        Initialize the client.

        Args:
            base_url: Base URL for eCUDO API
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts per request
        """
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en",
        }
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> "EcudoClient":
        """Enter async context - create session."""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout),
            headers=self.headers,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context - close session."""
        if self._session:
            await self._session.close()
            self._session = None

    @property
    def session(self) -> aiohttp.ClientSession:
        """Get the current session, raising if not initialized."""
        if not self._session:
            raise RuntimeError(
                "Client not initialized. Use 'async with EcudoClient() as client:'"
            )
        return self._session

    async def fetch_json(self, url: str) -> dict:
        """
        Fetch JSON from URL with retries and exponential backoff.

        Args:
            url: URL to fetch

        Returns:
            Parsed JSON as dict, or empty dict on failure
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                async with self.session.get(url, allow_redirects=True) as resp:
                    if resp.status == 200:
                        return await resp.json()

                    text = await resp.text()
                    output.error(f"❌ Error {resp.status} fetching {url}: {text[:100]}")
                    return {}
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt < self.max_retries:
                    wait = 2**attempt
                    output.debug(
                        f"⚠️ Attempt {attempt}/{self.max_retries} failed: {exc}. "
                        f"Retrying in {wait}s..."
                    )
                    await asyncio.sleep(wait)
                    continue

                output.error(
                    f"❌ All {self.max_retries} attempts failed for {url}: {exc}"
                )
                return {}
        return {}

    async def get_organizations(self) -> list[dict]:
        """
        Fetch list of organizations.

        Returns:
            List of organization dicts with 'id', 'name', 'link' keys
        """
        data = await self.fetch_json(f"{self.base_url}/organizations")
        return data.get("organizations", [])

    async def get_record_ids_page(
        self, org_id: str, offset: int, limit: int
    ) -> list[str]:
        """
        Fetch one page of record IDs for an organization.

        Args:
            org_id: Organization ID
            offset: Starting offset (1-based)
            limit: Number of records per page

        Returns:
            List of record IDs (URN format)
        """
        url = (
            f"{self.base_url}/organizations/{org_id}/data?offset={offset}&limit={limit}"
        )
        data = await self.fetch_json(url)
        return data.get("metadata", [])

    async def get_record_metadata(self, record_id: str) -> dict:
        """
        Fetch JSON-LD metadata for a single record.

        Args:
            record_id: Record identifier (URN format)

        Returns:
            Raw JSON-LD metadata dict, or empty dict on failure
        """
        url = f"{self.base_url}/metadata/{record_id}/json-ld"
        return await self.fetch_json(url)

    async def validate_url(self, url: str) -> bool:
        """
        Check if a URL is accessible using HEAD request.

        Args:
            url: URL to validate

        Returns:
            True if URL returns 200, False otherwise
        """
        try:
            async with self.session.head(url, allow_redirects=True) as resp:
                return resp.status == 200
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            output.debug(f"⚠️ URL validation failed for {url}: {exc}")
            return False
