# basescan_scraper/fetchers/base.py
from typing import Protocol


class FetchError(Exception):
    """Base class for all fetch failures."""


class UpstreamTimeout(FetchError):
    """Outbound request timed out."""


class UpstreamRateLimited(FetchError):
    """BaseScan rate-limited or blocked us (HTTP 429 / challenge)."""


class UpstreamUnavailable(FetchError):
    """BaseScan returned 5xx or an unusable response."""


class ResponseTooLarge(FetchError):
    """Response exceeded the configured size cap."""


class Fetcher(Protocol):
    async def get(self, path: str) -> str:
        """Fetch `path` (relative to base URL) and return decoded HTML.

        Implementations own retries, timeouts, size caps, rate-limit handling.
        `path` MUST already be validated/constructed by the caller — never pass
        raw user input here.
        """
        ...
