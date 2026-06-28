# tests/unit/test_http_fetcher.py
import httpx
import pytest
import respx

from basescan_scraper.config import Settings
from basescan_scraper.fetchers.base import (
    ResponseTooLarge,
    UpstreamRateLimited,
    UpstreamTimeout,
    UpstreamUnavailable,
)
from basescan_scraper.fetchers.http_fetcher import HttpFetcher

BASE = "https://basescan.org"


def _settings(**over):
    defaults = dict(FETCH_MAX_RETRIES=2, OUTBOUND_MIN_INTERVAL_SECONDS=0)
    defaults.update(over)
    return Settings(_env_file=None, BASESCAN_BASE_URL=BASE, **defaults)


@respx.mock
async def test_get_returns_html():
    respx.get(f"{BASE}/address/0xabc").mock(return_value=httpx.Response(200, html="<html>ok</html>"))
    f = HttpFetcher(_settings())
    body = await f.get("/address/0xabc")
    assert "ok" in body
    await f.aclose()


@respx.mock
async def test_429_raises_rate_limited():
    respx.get(f"{BASE}/x").mock(return_value=httpx.Response(429))
    f = HttpFetcher(_settings())
    with pytest.raises(UpstreamRateLimited):
        await f.get("/x")
    await f.aclose()


@respx.mock
async def test_5xx_retries_then_raises_unavailable():
    route = respx.get(f"{BASE}/x").mock(return_value=httpx.Response(503))
    f = HttpFetcher(_settings())
    with pytest.raises(UpstreamUnavailable):
        await f.get("/x")
    assert route.call_count == 3  # initial + 2 retries
    await f.aclose()


@respx.mock
async def test_5xx_retries_use_exponential_backoff(monkeypatch):
    from basescan_scraper.fetchers import http_fetcher as hf

    respx.get(f"{BASE}/x").mock(return_value=httpx.Response(503))

    sleeps: list[float] = []

    async def _fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(hf.asyncio, "sleep", _fake_sleep)

    f = HttpFetcher(_settings(FETCH_MAX_RETRIES=3, OUTBOUND_MIN_INTERVAL_SECONDS=0))
    with pytest.raises(UpstreamUnavailable):
        await f.get("/x")
    # 4 attempts, 3 backoff sleeps between them; throttle interval is 0 so it adds none.
    assert sleeps == [0.5, 1.0, 2.0]
    await f.aclose()


@respx.mock
async def test_timeout_raises_timeout():
    respx.get(f"{BASE}/x").mock(side_effect=httpx.ConnectTimeout("slow"))
    f = HttpFetcher(_settings())
    with pytest.raises(UpstreamTimeout):
        await f.get("/x")
    await f.aclose()


@respx.mock
async def test_oversize_response_rejected():
    big = "<html>" + ("a" * 1000) + "</html>"
    respx.get(f"{BASE}/x").mock(return_value=httpx.Response(200, html=big))
    f = HttpFetcher(_settings(MAX_RESPONSE_BYTES=100))
    with pytest.raises(ResponseTooLarge):
        await f.get("/x")
    await f.aclose()
