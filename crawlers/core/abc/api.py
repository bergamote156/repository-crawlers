"""API Client Base."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Self

import aiohttp  # type: ignore[import-not-found]

from crawlers.core.errors import ApiError, HttpError, HttpTimeoutError
from crawlers.core.result import Err, Ok, Result
from crawlers.core.ui import console


class ApiClient[OptsT, DatasetT](ABC):
    """
    Base API client with built-in HTTP handling.

    Generics:
        OptsT: Type of iterator options (e.g. EcudoIteratorOpts)
        DatasetT: Type yielded by the iterator (e.g. str for ID, dict for JSON)
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

    async def _request_json(
        self, method: str, url: str, **kwargs
    ) -> Result[dict, ApiError]:
        """
        Execute an HTTP request and return JSON response with retries and backoff.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: URL to request
            **kwargs: Extra arguments for the session.request()

        Returns:
            Ok(dict) on success, Err(ApiError) on failure
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                async with self.session.request(
                    method, url, allow_redirects=True, **kwargs
                ) as resp:
                    if resp.status == 200:
                        return Ok(await resp.json())

                    text = await resp.text()
                    return Err(
                        HttpError(
                            status=resp.status,
                            method=method,
                            url=url,
                            body=text[:200],
                        )
                    )
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt < self.max_retries:
                    wait = 2**attempt
                    console.debug(
                        f"Attempt {attempt}/{self.max_retries} failed for "
                        f"{method} {url}: {exc}. Retrying in {wait}s..."
                    )
                    await asyncio.sleep(wait)
                    continue

                return Err(
                    HttpTimeoutError(
                        method=method,
                        url=url,
                        attempts=self.max_retries,
                        last_error=str(exc),
                    )
                )

        # Unreachable, but satisfies type checker
        return Err(
            HttpTimeoutError(
                method=method, url=url, attempts=self.max_retries, last_error="unknown"
            )
        )

    async def get_json(self, url: str) -> Result[dict, ApiError]:
        """
        Fetch JSON from URL with retries and exponential backoff.

        Args:
            url: URL to fetch

        Returns:
            Ok(dict) on success, Err(ApiError) on failure
        """
        return await self._request_json("GET", url)

    async def post_json(self, url: str, body: dict) -> Result[dict, ApiError]:
        """
        POST JSON to URL and return response with retries and exponential backoff.

        Args:
            url: URL to post to
            body: JSON body to send

        Returns:
            Ok(dict) on success, Err(ApiError) on failure
        """
        return await self._request_json("POST", url, json=body)

    async def validate_url(self, url: str) -> Result[bool, ApiError]:
        """
        Check if a URL is accessible using HEAD request.

        Args:
            url: URL to validate

        Returns:
            Ok(True) if URL returns 200, Err(ApiError) on failure
        """
        try:
            async with self.session.head(url, allow_redirects=True) as resp:
                if resp.status == 200:
                    return Ok(True)

                return Err(HttpError(status=resp.status, method="HEAD", url=url))
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            return Err(
                HttpTimeoutError(
                    method="HEAD", url=url, attempts=1, last_error=str(exc)
                )
            )

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
