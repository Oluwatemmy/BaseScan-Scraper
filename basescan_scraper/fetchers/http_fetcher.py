# basescan_scraper/fetchers/http_fetcher.py
import asyncio

import httpx

from basescan_scraper.config import Settings
from basescan_scraper.fetchers.base import (
    ResponseTooLarge,
    UpstreamRateLimited,
    UpstreamTimeout,
    UpstreamUnavailable,
)

_BACKOFF_BASE_SECONDS = 0.5
_BACKOFF_CAP_SECONDS = 8.0

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

_JSON_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}


class HttpFetcher:
    """Approach A fetcher: plain async HTTP GET with retries, timeout, size cap,
    rate-limit detection, and outbound throttling."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.base_url,
            headers=_HEADERS,
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
        )
        self._throttle = asyncio.Lock()
        self._last_request_at = 0.0

    async def _wait_turn(self) -> None:
        interval = self._settings.outbound_min_interval_seconds
        if interval <= 0:
            return
        async with self._throttle:
            now = asyncio.get_running_loop().time()
            delta = now - self._last_request_at
            if delta < interval:
                await asyncio.sleep(interval - delta)
            self._last_request_at = asyncio.get_running_loop().time()

    async def _backoff(self, attempt: int, total_attempts: int) -> None:
        """Sleep with exponential backoff before the next retry. `attempt` is the
        0-based index of the just-failed attempt; no sleep after the last one."""
        if attempt + 1 >= total_attempts:
            return
        delay = min(_BACKOFF_CAP_SECONDS, _BACKOFF_BASE_SECONDS * (2 ** attempt))
        await asyncio.sleep(delay)

    async def _request(
        self, method: str, path: str, json_body: dict | None = None
    ) -> str:
        retries = self._settings.fetch_max_retries
        last_exc: Exception | None = None
        total_attempts = retries + 1
        for attempt in range(total_attempts):
            await self._wait_turn()
            try:
                if method == "POST":
                    resp = await self._client.post(
                        path, json=json_body, headers=_JSON_HEADERS
                    )
                else:
                    resp = await self._client.get(path)
            except httpx.TimeoutException as exc:
                last_exc = exc
                await self._backoff(attempt, total_attempts)
                continue
            except httpx.HTTPError as exc:
                last_exc = exc
                await self._backoff(attempt, total_attempts)
                continue

            if resp.status_code == 429:
                raise UpstreamRateLimited(f"429 for {path}")
            if resp.status_code >= 500:
                last_exc = UpstreamUnavailable(f"{resp.status_code} for {path}")
                await self._backoff(attempt, total_attempts)
                continue
            if resp.status_code >= 400:
                raise UpstreamUnavailable(f"{resp.status_code} for {path}")

            body = resp.content
            if len(body) > self._settings.max_response_bytes:
                raise ResponseTooLarge(f"{len(body)} bytes for {path}")
            return resp.text

        if isinstance(last_exc, httpx.TimeoutException):
            raise UpstreamTimeout(str(last_exc)) from last_exc
        raise UpstreamUnavailable(str(last_exc)) from last_exc

    async def get(self, path: str) -> str:
        return await self._request("GET", path)

    async def post_json(self, path: str, body: dict) -> str:
        return await self._request("POST", path, json_body=body)

    async def aclose(self) -> None:
        await self._client.aclose()
