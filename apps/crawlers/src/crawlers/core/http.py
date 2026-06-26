"""HTTP client with retries, exponential backoff, and `Result`-based errors."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2026 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from http import HTTPStatus
from importlib.metadata import PackageNotFoundError, version
from typing import Protocol, Self
from urllib.parse import urljoin

import aiohttp  # type: ignore[import-not-found]

from crawlers.core.result import Err, JsonObject, JsonValue, Ok, Result
from crawlers.ui import console


# pylint: disable=too-few-public-methods
class HttpConfigLike(Protocol):
    """Minimum config shape consumed by `HttpClient.from_config`."""

    base_url: str
    timeout: int
    max_retries: int


@dataclass(frozen=True)
class ResponseFailure:
    """Non-200 HTTP response."""

    status: int
    method: str
    url: str
    body: str = ""

    def to_json(self) -> dict:
        """Serialize to a JSON-safe dict."""
        return {"type": "http_failure", **asdict(self)}

    def __str__(self) -> str:
        return f"HTTP {self.status} {self.method} {self.url}"


@dataclass(frozen=True)
class TimeoutFailure:
    """All retry attempts exhausted due to network/timeout errors."""

    method: str
    url: str
    attempts: int
    last_error: str

    def to_json(self) -> dict:
        """Serialize to a JSON-safe dict."""
        return {"type": "timeout_failure", **asdict(self)}

    def __str__(self) -> str:
        return f"Timeout after {self.attempts} attempts: {self.method} {self.url}"


type HttpFailure = ResponseFailure | TimeoutFailure


class HttpClient:
    """
    Async HTTP client with built-in retries, exponential backoff, and `Result`-based errors.

    Provides low-level byte/text fetchers and JSON convenience wrappers, all sharing
    the same retry policy. Use as an async context manager:

        async with HttpClient(base_url="https://example.org", user_agent="MyCrawler/1.0") as http:
            result = await http.get_json("/api/items")

    When `base_url` is set, request URLs may be either relative paths (resolved
    against `base_url`) or absolute URLs (used as-is, even if they point to a
    different host — useful e.g. for server-provided pagination links).
    """

    def __init__(  # noqa: PLR0913
        self,
        *,
        base_url: str | None = None,
        user_agent: str | None = None,
        extra_headers: dict[str, str] | None = None,
        timeout: int = 15,
        max_retries: int = 3,
        verify_ssl: bool = True,
    ):
        """
        Initialize the client.

        Args:
            base_url: Optional base URL. If set, relative URLs passed to request
                methods are resolved against it; absolute URLs are passed through.
            user_agent: Override the default `OnedataCrawler/<version>` UA string.
            extra_headers: Additional headers merged into every request. Must not
                contain `User-Agent` — use `user_agent` for that.
            timeout: Total request timeout in seconds.
            max_retries: Maximum retry attempts per request on network/timeout errors.
            verify_ssl: Verify server TLS certificates. Disabling is a security
                decision and is logged as a warning on session start.
        """
        if extra_headers and "User-Agent" in extra_headers:
            raise ValueError("Set User-Agent via the `user_agent` parameter, not `extra_headers`.")

        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.verify_ssl = verify_ssl
        self.headers = {
            "User-Agent": user_agent or _default_user_agent(),
            "Accept": "application/json, text/plain, */*",
            **(extra_headers or {}),
        }
        self._session: aiohttp.ClientSession | None = None

    @classmethod
    def from_config(cls, config: HttpConfigLike, **overrides) -> Self:
        """
        Build an `HttpClient` from a config object exposing HTTP settings.

        Any keyword in `overrides` wins over the config value — useful for
        injecting plugin-specific headers or flipping `verify_ssl` in dev.
        """
        kwargs: dict = {
            "base_url": config.base_url,
            "timeout": config.timeout,
            "max_retries": config.max_retries,
        }
        kwargs.update(overrides)
        return cls(**kwargs)

    async def __aenter__(self) -> Self:
        """Open the underlying aiohttp session."""
        if not self.verify_ssl:
            console.warning(
                "HttpClient: TLS certificate verification is DISABLED. "
                "This should only be used in trusted/dev environments."
            )
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout),
            headers=self.headers,
            connector=aiohttp.TCPConnector(ssl=self.verify_ssl),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close the underlying aiohttp session."""
        if self._session:
            await self._session.close()
            self._session = None

    @property
    def session(self) -> aiohttp.ClientSession:
        """Return the live aiohttp session, raising if the client is not entered."""
        if not self._session:
            raise RuntimeError(
                "HttpClient not initialized. Use 'async with HttpClient(...) as http:'"
            )
        return self._session

    async def head(self, url: str, **kwargs) -> Result[None, HttpFailure]:
        """
        HEAD `url` to check accessibility.

        Returns `Ok(None)` on a 2xx response, `Err(HttpFailure)` on any non-2xx,
        `Err(TimeoutFailure)` after exhausting retries on network errors.
        """
        # return await self._request("GET", url, lambda _: _noop(), **kwargs)
        return None  # HEAD requests are currently disabled due to some servers mishandling them

    async def get_bytes(self, url: str, **kwargs) -> Result[bytes, HttpFailure]:
        """GET `url` and return the raw response body."""
        return await self._request("GET", url, lambda r: r.read(), **kwargs)

    async def get_text(self, url: str, **kwargs) -> Result[str, HttpFailure]:
        """GET `url` and return the response body decoded as text."""
        return await self._request("GET", url, lambda r: r.text(), **kwargs)

    async def get_json(self, url: str, **kwargs) -> Result[JsonValue, HttpFailure]:
        """GET `url` and return the response body parsed as JSON."""
        return await self._request("GET", url, lambda r: r.json(), **kwargs)

    async def post_json(
        self, url: str, body: JsonObject, **kwargs
    ) -> Result[JsonValue, HttpFailure]:
        """POST `body` as JSON to `url` and return the response parsed as JSON."""
        return await self._request("POST", url, lambda r: r.json(), json=body, **kwargs)

    async def get_json_object(self, url: str, **kwargs) -> Result[JsonObject, HttpFailure]:
        """GET `url` and return the response body as a JSON object.

        Returns `Err(ResponseFailure)` if the response is valid JSON but not
        an object (e.g. an array or primitive).
        """
        return await self._expect_object("GET", url, await self.get_json(url, **kwargs))

    async def post_json_object(
        self, url: str, body: JsonObject, **kwargs
    ) -> Result[JsonObject, HttpFailure]:
        """POST `body` as JSON and return the response as a JSON object.

        Returns `Err(ResponseFailure)` if the response is valid JSON but not
        an object (e.g. an array or primitive).
        """
        return await self._expect_object("POST", url, await self.post_json(url, body, **kwargs))

    async def _expect_object(
        self,
        method: str,
        url: str,
        result: Result[JsonValue, HttpFailure],
    ) -> Result[JsonObject, HttpFailure]:
        """Narrow a JSON result to a dict, or return an error."""
        match result:
            case Ok(value=v) if isinstance(v, dict):
                return Ok(v)
            case Ok(value=v):
                return Err(
                    ResponseFailure(
                        status=200,
                        method=method,
                        url=self._resolve(url),
                        body=f"expected JSON object, got {type(v).__name__}",
                    )
                )
            case err:
                return err

    async def _request[T](
        self,
        method: str,
        url: str,
        read: Callable[[aiohttp.ClientResponse], Awaitable[T]],
        **kwargs,
    ) -> Result[T, HttpFailure]:
        """
        Execute an HTTP request with retries and read the body via `read`.

        On a 2xx response, the body is materialized through `read` (e.g. `resp.json`,
        `resp.text`, `resp.read`) before the connection is released, so the returned
        value is safe to use after the context manager exits.

        Args:
            method: HTTP method (GET, POST, ...).
            url: Target URL. Relative URLs are resolved against `base_url` if set.
            read: Coroutine consuming the response and producing the result value.
            **kwargs: Forwarded to `aiohttp.ClientSession.request`.

        Returns:
            `Ok(value)` on a 2xx response, `Err(HttpFailure)` on non-2xx,
            `Err(TimeoutFailure)` after exhausting retries on network errors.
        """
        resolved_url = self._resolve(url)
        for attempt in range(1, self.max_retries + 1):
            try:
                async with self.session.request(
                    method, resolved_url, allow_redirects=True, **kwargs
                ) as resp:
                    if HTTPStatus.OK <= resp.status < HTTPStatus.MULTIPLE_CHOICES:
                        return Ok(await read(resp))

                    text = await resp.text()
                    return Err(
                        ResponseFailure(
                            status=resp.status,
                            method=method,
                            url=resolved_url,
                            body=text[:200],
                        )
                    )
            except (aiohttp.ClientError, TimeoutError) as exc:
                if attempt < self.max_retries:
                    wait = 2**attempt
                    console.debug(
                        f"Attempt {attempt}/{self.max_retries} failed for "
                        f"{method} {resolved_url}: {exc}. Retrying in {wait}s..."
                    )
                    await asyncio.sleep(wait)
                    continue

                return Err(
                    TimeoutFailure(
                        method=method,
                        url=resolved_url,
                        attempts=self.max_retries,
                        last_error=str(exc),
                    )
                )

        # Unreachable, but satisfies type checker
        return Err(  # pylint: disable=unreachable
            TimeoutFailure(
                method=method,
                url=resolved_url,
                attempts=self.max_retries,
                last_error="unknown",
            )
        )

    def _resolve(self, url: str) -> str:
        """Resolve `url` against `base_url` if set; absolute URLs pass through."""
        if self.base_url is None:
            return url

        return urljoin(self.base_url.rstrip("/") + "/", url.lstrip("/"))


async def _noop() -> None:
    """Awaitable that returns None — used as a body reader for HEAD requests."""
    return None


def _default_user_agent() -> str:
    """Build the default `OnedataCrawler/<version>` UA string."""
    try:
        ver = version("repository-crawlers")
    except PackageNotFoundError:
        ver = "dev"
    return f"OnedataCrawler/{ver} (+https://onedata.org; mailto:info@onedata.org)"
