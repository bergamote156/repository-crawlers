"""API Client Base."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import asyncio
from abc import ABC, abstractmethod
from typing import AsyncIterator, Self

import aiohttp  # type: ignore[import-not-found]

from crawlers.core import output


class ApiClient[OptsT, DatasetT](ABC):
    """
    Base API client with built-in HTTP handling.

    Generics:
        T: Type yielded by the iterator (e.g. str for ID, dict for JSON)
        P: Type of iterator options (e.g. EcudoIteratorOpts)
    """

    def __init__(
        self,
        base_url: str,
        timeout: int = 15,
        max_retries: int = 3,
    ):
        """
        Initialize the client.

        Args:
            base_url: Base URL for the external service API
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
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> Self:
        """Create HTTP session."""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout),
            headers=self.headers,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None

    @property
    def session(self) -> aiohttp.ClientSession:
        """Get the current session, raising if not initialized."""
        if not self._session:
            raise RuntimeError(
                "Client not initialized. Use 'async with ApiClient(...) as client:'"
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
                    output.error(f"Error {resp.status} fetching {url}: {text[:100]}")
                    return {}
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt < self.max_retries:
                    wait = 2**attempt
                    output.debug(
                        f"Attempt {attempt}/{self.max_retries} failed for {url}: {exc}. "
                        f"Retrying in {wait}s..."
                    )
                    await asyncio.sleep(wait)
                    continue

                output.error(f"All {self.max_retries} attempts failed for {url}: {exc}")
                return {}
        return {}

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
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False

    @abstractmethod
    def iterate_datasets(self, opts: OptsT) -> AsyncIterator[DatasetT]:
        """
        Iterate over datasets.

        Args:
            opts: Iterator options specific to the plugin

        Yields:
            T: Dataset item (ID, dict, or other type depending on plugin)
        """
        raise NotImplementedError
