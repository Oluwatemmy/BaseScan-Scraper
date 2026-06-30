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


@respx.mock
async def test_redirect_not_followed():
    # A 3xx must NOT be chased — SSRF-via-redirect guard. The target is never hit.
    target = respx.get(f"{BASE}/internal").mock(
        return_value=httpx.Response(200, html="secret"))
    respx.get(f"{BASE}/x").mock(
        return_value=httpx.Response(302, headers={"Location": f"{BASE}/internal"}))
    f = HttpFetcher(_settings())
    with pytest.raises(UpstreamUnavailable):
        await f.get("/x")
    assert target.call_count == 0  # redirect target never requested
    await f.aclose()


@respx.mock
async def test_oversize_streamed_without_content_length_aborts():
    # No Content-Length (chunked) body over the cap must still be rejected via
    # the streaming early-abort, not buffered whole.
    async def gen():
        for _ in range(50):
            yield b"a" * 50  # 2500 bytes total, streamed, no Content-Length

    respx.get(f"{BASE}/x").mock(return_value=httpx.Response(200, content=gen()))
    f = HttpFetcher(_settings(MAX_RESPONSE_BYTES=100))
    with pytest.raises(ResponseTooLarge):
        await f.get("/x")
    await f.aclose()


@respx.mock
async def test_post_json_returns_text():
    route = respx.post(f"{BASE}/x.aspx/Get").mock(
        return_value=httpx.Response(200, json={"d": {"ok": 1}}))
    f = HttpFetcher(_settings())
    body = await f.post_json("/x.aspx/Get", {"a": 1})
    assert '"ok"' in body
    sent = route.calls.last.request
    assert sent.headers["content-type"].startswith("application/json")
    assert sent.headers["x-requested-with"] == "XMLHttpRequest"
    await f.aclose()


@respx.mock
async def test_post_json_5xx_retries_then_raises():
    route = respx.post(f"{BASE}/x").mock(return_value=httpx.Response(503))
    f = HttpFetcher(_settings())
    with pytest.raises(UpstreamUnavailable):
        await f.post_json("/x", {})
    assert route.call_count == 3
    await f.aclose()
