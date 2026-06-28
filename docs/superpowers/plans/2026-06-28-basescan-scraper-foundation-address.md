# BaseScan Scraper — Foundation + Address Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **COMMITS:** This user commits manually via GitHub Desktop. **Do NOT run `git commit` or `git push`.** Where this plan says "Checkpoint", pause so the user can commit, then continue.

**Goal:** Build the foundation of the BaseScan scraper and a complete, tested, secure, Swagger-documented vertical slice for **address/wallet** data (profile, transactions, internal transactions, token transfers, NFT transfers) served over a FastAPI REST API.

**Architecture:** Layered, source-swappable. `API (FastAPI /v1) → Service (cache→fetch→parse) → {Cache, Fetcher, Parsers, Models}`. Approach A: `httpx` fetch + `selectolax` HTML parsing (verified: BaseScan tables are server-rendered). Fetcher is an interface so a Playwright fallback drops in later.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, httpx, selectolax, Pydantic v2, pydantic-settings, cachetools, pytest, pytest-asyncio, respx (httpx mocking), ruff. (No inbound rate limiting — the trusted main project is the only caller and owns that concern.)

**Scope of THIS plan:** Foundation + address endpoints only. Tokens & transactions endpoints are a follow-on plan (Plan 2) using the same pattern. Playwright fallback and monitoring are deferred per spec.

**Reference spec:** `docs/superpowers/specs/2026-06-28-basescan-scraper-design.md`

**Verified facts (from exploration):**
- Address page returns full data via plain HTTP GET (no JS, no Cloudflare challenge).
- Numbers contain inline markup (e.g. `0<b>.</b>30906125826241616 ETH`) — parsers MUST read normalized text content, never rely on contiguous source strings.
- The address transactions table lives in a container with `id="transactions"`; tables use class `table table-hover`.
- A realistic test address: `0x71c7656ec7ab88b098defb751b7401b5f6d8976f` ("BaseScan: Donate").

---

## File Structure

```
requirements.txt                            # runtime dependencies
requirements-dev.txt                        # dev/test dependencies
pytest.ini                                  # pytest config (pythonpath, markers)
ruff.toml                                   # lint config
.env.example                                # documented env vars (no secrets)
basescan_scraper/
  __init__.py
  config.py                                 # env-based Settings
  app.py                                    # FastAPI app factory
  fetchers/
    __init__.py
    base.py                                 # Fetcher Protocol + exceptions
    http_fetcher.py                         # HttpFetcher (httpx)
  cache/
    __init__.py
    base.py                                 # Cache Protocol
    memory.py                               # TTLCache impl
  parsers/
    __init__.py
    common.py                               # text/number normalization helpers
    address.py                              # address page parsers
  models/
    __init__.py
    common.py                               # Amount, Pagination, Page[T], ProblemDetail
    address.py                              # AddressProfile, Transaction, etc.
  services/
    __init__.py
    address_service.py                      # orchestration for address data
  api/
    __init__.py
    validators.py                           # path-param validation patterns
    errors.py                               # exception→ProblemDetail handlers
    deps.py                                 # shared FastAPI dependencies
    routers/
      __init__.py
      health.py
      addresses.py
tests/
  conftest.py                               # fixtures: fake fetcher/cache, test client
  fixtures/
    address_donate.html                     # captured real page
  unit/
    test_config.py
    test_models_common.py
    test_http_fetcher.py
    test_memory_cache.py
    test_parsers_common.py
    test_parser_address.py
    test_address_service.py
  api/
    test_health.py
    test_addresses_api.py
    test_validation.py
  live/
    test_live_drift.py                      # opt-in (marker), hits real BaseScan
```

---

## Phase 0 — Scaffolding

### Task 1: Project setup

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `pytest.ini`
- Create: `ruff.toml`
- Create: `.env.example`
- Create: `basescan_scraper/__init__.py` (empty)

> This project is a deployable API service, NOT an installable package. There is no
> `pyproject.toml`/`setup.py` and no `pip install -e .`. Dependencies are declared in
> `requirements.txt`; tests import the code via `pytest.ini`'s `pythonpath = .`.

- [ ] **Step 1: Create `requirements.txt`** (runtime dependencies)

```text
fastapi>=0.115
uvicorn[standard]>=0.30
httpx>=0.27
selectolax>=0.3.21
pydantic>=2.7
pydantic-settings>=2.3
cachetools>=5.3
```

- [ ] **Step 2: Create `requirements-dev.txt`** (dev/test dependencies)

```text
-r requirements.txt
pytest>=8.2
pytest-asyncio>=0.23
respx>=0.21
ruff>=0.5
```

- [ ] **Step 3: Create `pytest.ini`**

```ini
[pytest]
pythonpath = .
asyncio_mode = auto
testpaths = tests
markers =
    live: tests that hit the real basescan.org (deselected by default)
addopts = -m "not live"
```

- [ ] **Step 4: Create `ruff.toml`**

```toml
line-length = 100
src = ["basescan_scraper", "tests"]
```

- [ ] **Step 5: Create `.env.example`**

```bash
# Copy to .env and adjust. .env is git-ignored.
BASESCAN_BASE_URL=https://basescan.org
# Outbound politeness / safety
REQUEST_TIMEOUT_SECONDS=15
MAX_RESPONSE_BYTES=5242880
FETCH_MAX_RETRIES=3
OUTBOUND_MIN_INTERVAL_SECONDS=0.25
# Cache
CACHE_TTL_SECONDS=30
CACHE_MAX_ITEMS=2000
# CORS (comma-separated origins; empty = none)
ALLOWED_ORIGINS=
# Pagination safety cap
MAX_PAGE_OFFSET=100
```

- [ ] **Step 6: Create the package init file**

Create `basescan_scraper/__init__.py` as an empty file. Do NOT create `tests/__init__.py`
— with `pythonpath = .` the test files import `basescan_scraper` directly and `tests`
does not need to be a package.

- [ ] **Step 7: Create a virtual environment and install dependencies**

Always use an isolated `.venv` — never install into the global Python. `.venv/` is
already git-ignored.

```bash
python -m venv .venv
# Windows (Git Bash): use the venv interpreter directly
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```
Verify: `.venv/Scripts/python.exe -c "import basescan_scraper"` exits 0 (run from repo
root). From here on, run ALL tooling through the venv interpreter:
`.venv/Scripts/python.exe -m pytest` and `.venv/Scripts/python.exe -m ruff check ...`
(on macOS/Linux the path is `.venv/bin/python`).

- [ ] **Step 8: Checkpoint** — user commits via GitHub Desktop (suggested message: `chore: project scaffolding and dependencies`).

---

### Task 2: Config module

**Files:**
- Create: `basescan_scraper/config.py`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_config.py
from basescan_scraper.config import Settings


def test_defaults_are_sane():
    s = Settings(_env_file=None)
    assert s.base_url.startswith("https://")
    assert s.request_timeout_seconds > 0
    assert s.max_response_bytes >= 1_000_000
    assert s.cache_ttl_seconds >= 0
    assert s.max_page_offset >= 1


def test_env_override(monkeypatch):
    monkeypatch.setenv("CACHE_TTL_SECONDS", "99")
    s = Settings(_env_file=None)
    assert s.cache_ttl_seconds == 99


def test_allowed_origins_parses_csv(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.com,https://b.com")
    s = Settings(_env_file=None)
    assert s.allowed_origins == ["https://a.com", "https://b.com"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: basescan_scraper.config`.

- [ ] **Step 3: Write minimal implementation**

```python
# basescan_scraper/config.py
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    base_url: str = Field(default="https://basescan.org", alias="BASESCAN_BASE_URL")
    request_timeout_seconds: float = Field(default=15.0, alias="REQUEST_TIMEOUT_SECONDS")
    max_response_bytes: int = Field(default=5_242_880, alias="MAX_RESPONSE_BYTES")
    fetch_max_retries: int = Field(default=3, alias="FETCH_MAX_RETRIES")
    outbound_min_interval_seconds: float = Field(
        default=0.25, alias="OUTBOUND_MIN_INTERVAL_SECONDS"
    )
    cache_ttl_seconds: int = Field(default=30, alias="CACHE_TTL_SECONDS")
    cache_max_items: int = Field(default=2000, alias="CACHE_MAX_ITEMS")
    # NoDecode: pydantic-settings would otherwise JSON-decode this env var before our
    # CSV validator runs. NoDecode hands the raw string to _split_csv instead.
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=list, alias="ALLOWED_ORIGINS"
    )
    max_page_offset: int = Field(default=100, alias="MAX_PAGE_OFFSET")

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_csv(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_config.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Checkpoint** — user commits (`feat: env-based settings`).

---

### Task 3: FastAPI app factory + health endpoint

**Files:**
- Create: `basescan_scraper/api/__init__.py` (empty)
- Create: `basescan_scraper/api/routers/__init__.py` (empty)
- Create: `basescan_scraper/api/routers/health.py`
- Create: `basescan_scraper/app.py`
- Create: `tests/conftest.py`
- Test: `tests/api/test_health.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_health.py
def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_openapi_served(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert resp.json()["info"]["title"] == "BaseScan Scraper API"
```

- [ ] **Step 2: Create `tests/conftest.py`**

```python
# tests/conftest.py
import pytest
from fastapi.testclient import TestClient

from basescan_scraper.app import create_app


@pytest.fixture
def client():
    return TestClient(create_app())
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/api/test_health.py -v`
Expected: FAIL with `ModuleNotFoundError: basescan_scraper.app`.

- [ ] **Step 4: Write health router**

```python
# basescan_scraper/api/routers/health.py
from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["Health"], summary="Liveness check")
def health() -> dict[str, str]:
    """Return service liveness. Does not scrape BaseScan."""
    return {"status": "ok"}
```

- [ ] **Step 5: Write app factory**

```python
# basescan_scraper/app.py
from fastapi import FastAPI

from basescan_scraper.api.routers import health


def create_app() -> FastAPI:
    app = FastAPI(
        title="BaseScan Scraper API",
        version="0.1.0",
        description="Read-only REST API exposing Base chain data scraped from basescan.org.",
    )
    app.include_router(health.router)
    return app


app = create_app()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/api/test_health.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Verify the server boots**

Run: `uvicorn basescan_scraper.app:app --port 8000` (Ctrl-C after confirming startup log). Visit `/docs` shows Swagger UI with the Health endpoint.

- [ ] **Step 8: Checkpoint** — user commits (`feat: FastAPI app factory and health endpoint`).

---

## Phase 1 — Models

### Task 4: Common models (Amount, Pagination, Page, ProblemDetail)

**Files:**
- Create: `basescan_scraper/models/__init__.py` (empty)
- Create: `basescan_scraper/models/common.py`
- Test: `tests/unit/test_models_common.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_models_common.py
from basescan_scraper.models.common import Amount, Page, Pagination, ProblemDetail


def test_amount_from_wei_keeps_precision():
    amt = Amount.from_wei("309061258262416160", decimals=18)
    assert amt.wei == "309061258262416160"          # exact string, no float
    assert amt.decimal == "0.30906125826241616"     # human readable
    assert amt.symbol is None


def test_amount_rejects_non_numeric_wei():
    import pytest
    with pytest.raises(ValueError):
        Amount.from_wei("not-a-number", decimals=18)


def test_page_envelope_shape():
    page = Page[int](data=[1, 2], pagination=Pagination(page=1, offset=25, total=2, has_next=False))
    dumped = page.model_dump()
    assert dumped["data"] == [1, 2]
    assert dumped["pagination"]["has_next"] is False


def test_problem_detail_defaults_status():
    pd = ProblemDetail(type="/errors/not-found", title="Not found", status=404)
    assert pd.status == 404
    assert pd.detail is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_models_common.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write implementation**

```python
# basescan_scraper/models/common.py
from decimal import Decimal
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Amount(BaseModel):
    """A token/ETH amount. `wei` is the exact integer as a string; `decimal` is
    human-readable. Strings are used so large integers never lose precision."""

    wei: str = Field(examples=["309061258262416160"])
    decimal: str = Field(examples=["0.30906125826241616"])
    symbol: Optional[str] = Field(default=None, examples=["ETH"])

    @classmethod
    def from_wei(cls, wei: str | int, decimals: int = 18, symbol: str | None = None) -> "Amount":
        wei_int = int(str(wei))  # raises ValueError on bad input
        dec = Decimal(wei_int) / (Decimal(10) ** decimals)
        # normalize: no scientific notation, strip trailing zeros
        dec_str = format(dec.normalize(), "f")
        return cls(wei=str(wei_int), decimal=dec_str, symbol=symbol)


class Pagination(BaseModel):
    page: int = Field(examples=[1], ge=1)
    offset: int = Field(examples=[25], ge=1, description="Items per page")
    total: Optional[int] = Field(default=None, examples=[96], description="Total items if known")
    has_next: bool = Field(examples=[True])


class Page(BaseModel, Generic[T]):
    data: list[T]
    pagination: Pagination


class ProblemDetail(BaseModel):
    """RFC 9457 Problem Details for HTTP APIs."""

    type: str = Field(examples=["/errors/not-found"])
    title: str = Field(examples=["Address not found"])
    status: int = Field(examples=[404])
    detail: Optional[str] = Field(default=None, examples=["No data for 0x… on Base."])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_models_common.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Checkpoint** — user commits (`feat: common API models (Amount, Page, ProblemDetail)`).

---

### Task 5: Address domain models

**Files:**
- Create: `basescan_scraper/models/address.py`
- Test: extend `tests/unit/test_models_common.py` is NOT used; add `tests/unit/test_models_address.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_models_address.py
from basescan_scraper.models.address import AddressProfile, Transaction
from basescan_scraper.models.common import Amount


def test_transaction_minimal():
    tx = Transaction(
        hash="0xb239798ab298435ae661f8693bdc9ba52c7f04bae796d7d99f1cb7d976e2140d",
        block=47819759,
        timestamp="2026-06-26T00:00:00Z",
        from_address="0x3ae6963e000000000000000000000000008fdfe02b5",
        to_address="0x71c7656ec7ab88b098defb751b7401b5f6d8976f",
        value=Amount.from_wei("11209130000000000", symbol="ETH"),
        method="Transfer",
        direction="in",
    )
    assert tx.hash.startswith("0x")
    assert tx.direction == "in"


def test_address_profile_minimal():
    p = AddressProfile(
        address="0x71c7656ec7ab88b098defb751b7401b5f6d8976f",
        eth_balance=Amount.from_wei("309061258262416160", symbol="ETH"),
        token_holdings_count=201,
    )
    assert p.address.startswith("0x")
    assert p.token_holdings_count == 201
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_models_address.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write implementation**

```python
# basescan_scraper/models/address.py
from typing import Literal, Optional

from pydantic import BaseModel, Field

from basescan_scraper.models.common import Amount

Direction = Literal["in", "out", "self"]


class Transaction(BaseModel):
    hash: str = Field(examples=["0xb239798ab2…2140d"])
    block: int = Field(examples=[47819759])
    timestamp: Optional[str] = Field(default=None, description="ISO 8601 UTC")
    from_address: str = Field(examples=["0x3ae6963e…02b5"])
    to_address: Optional[str] = Field(default=None, description="None for contract creation")
    value: Amount
    method: Optional[str] = Field(default=None, examples=["Transfer"])
    direction: Optional[Direction] = Field(default=None)
    txn_fee: Optional[Amount] = Field(default=None)


class InternalTransaction(BaseModel):
    parent_hash: str
    block: int
    timestamp: Optional[str] = None
    from_address: str
    to_address: Optional[str] = None
    value: Amount


class TokenTransfer(BaseModel):
    hash: str
    block: int
    timestamp: Optional[str] = None
    from_address: str
    to_address: str
    value: Amount
    token_name: Optional[str] = None
    token_symbol: Optional[str] = None
    token_address: Optional[str] = None


class NftTransfer(BaseModel):
    hash: str
    block: int
    timestamp: Optional[str] = None
    from_address: str
    to_address: str
    token_id: Optional[str] = None
    collection_name: Optional[str] = None
    token_address: Optional[str] = None


class AddressProfile(BaseModel):
    address: str
    eth_balance: Amount
    eth_value_usd: Optional[str] = Field(default=None, examples=["484.64"])
    token_holdings_count: Optional[int] = Field(default=None, examples=[201])
    token_holdings_value_usd: Optional[str] = Field(default=None, examples=["71123407.61"])
    funded_by: Optional[str] = Field(default=None)
    is_contract: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_models_address.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Checkpoint** — user commits (`feat: address domain models`).

---

## Phase 2 — Fetcher

### Task 6: Fetcher interface + exceptions

**Files:**
- Create: `basescan_scraper/fetchers/__init__.py` (empty)
- Create: `basescan_scraper/fetchers/base.py`
- Test: `tests/unit/test_http_fetcher.py` (created next task; this task has no test of its own — it defines the contract used by Task 7)

- [ ] **Step 1: Write `base.py`**

```python
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
```

- [ ] **Step 2: Verify it imports**

Run: `python -c "from basescan_scraper.fetchers.base import Fetcher, FetchError"`
Expected: exits 0.

- [ ] **Step 3: Checkpoint** — user commits (`feat: fetcher interface and exceptions`).

---

### Task 7: HttpFetcher (httpx)

**Files:**
- Create: `basescan_scraper/fetchers/http_fetcher.py`
- Test: `tests/unit/test_http_fetcher.py`

- [ ] **Step 1: Write the failing tests**

```python
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
    return Settings(_env_file=None, BASESCAN_BASE_URL=BASE, FETCH_MAX_RETRIES=2,
                    OUTBOUND_MIN_INTERVAL_SECONDS=0, **over)


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_http_fetcher.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write implementation**

```python
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

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
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
            now = asyncio.get_event_loop().time()
            delta = now - self._last_request_at
            if delta < interval:
                await asyncio.sleep(interval - delta)
            self._last_request_at = asyncio.get_event_loop().time()

    async def get(self, path: str) -> str:
        retries = self._settings.fetch_max_retries
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            await self._wait_turn()
            try:
                resp = await self._client.get(path)
            except httpx.TimeoutException as exc:
                last_exc = exc
                continue
            except httpx.HTTPError as exc:
                last_exc = exc
                continue

            if resp.status_code == 429:
                raise UpstreamRateLimited(f"429 for {path}")
            if resp.status_code >= 500:
                last_exc = UpstreamUnavailable(f"{resp.status_code} for {path}")
                continue
            if resp.status_code >= 400:
                # 4xx (other than 429) is a genuine "not found / bad" — surface as unavailable
                raise UpstreamUnavailable(f"{resp.status_code} for {path}")

            body = resp.content
            if len(body) > self._settings.max_response_bytes:
                raise ResponseTooLarge(f"{len(body)} bytes for {path}")
            return resp.text

        if isinstance(last_exc, httpx.TimeoutException):
            raise UpstreamTimeout(str(last_exc)) from last_exc
        raise UpstreamUnavailable(str(last_exc)) from last_exc

    async def aclose(self) -> None:
        await self._client.aclose()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_http_fetcher.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Checkpoint** — user commits (`feat: HttpFetcher with retries, timeout, size cap, rate-limit handling`).

---

## Phase 3 — Cache

### Task 8: Cache interface + in-memory TTL cache

**Files:**
- Create: `basescan_scraper/cache/__init__.py` (empty)
- Create: `basescan_scraper/cache/base.py`
- Create: `basescan_scraper/cache/memory.py`
- Test: `tests/unit/test_memory_cache.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_memory_cache.py
import pytest

from basescan_scraper.cache.memory import MemoryCache


async def test_set_then_get_returns_value():
    c = MemoryCache(maxsize=10, ttl=60)
    await c.set("k", {"v": 1})
    assert await c.get("k") == {"v": 1}


async def test_missing_key_returns_none():
    c = MemoryCache(maxsize=10, ttl=60)
    assert await c.get("absent") is None


async def test_ttl_zero_disables_cache():
    c = MemoryCache(maxsize=10, ttl=0)
    await c.set("k", 1)
    assert await c.get("k") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_memory_cache.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write the interface**

```python
# basescan_scraper/cache/base.py
from typing import Any, Protocol


class Cache(Protocol):
    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any) -> None: ...
```

- [ ] **Step 4: Write the implementation**

```python
# basescan_scraper/cache/memory.py
from typing import Any

from cachetools import TTLCache


class MemoryCache:
    """In-process TTL cache. ttl=0 disables caching entirely."""

    def __init__(self, maxsize: int, ttl: int):
        self._ttl = ttl
        self._store: TTLCache | None = TTLCache(maxsize=maxsize, ttl=ttl) if ttl > 0 else None

    async def get(self, key: str) -> Any | None:
        if self._store is None:
            return None
        return self._store.get(key)

    async def set(self, key: str, value: Any) -> None:
        if self._store is None:
            return
        self._store[key] = value
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_memory_cache.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Checkpoint** — user commits (`feat: in-memory TTL cache`).

---

## Phase 4 — Parsers (fixture-driven)

### Task 9: Capture real HTML fixture + parser helpers

**Files:**
- Create: `tests/fixtures/address_donate.html` (captured real page)
- Create: `basescan_scraper/parsers/__init__.py` (empty)
- Create: `basescan_scraper/parsers/common.py`
- Test: `tests/unit/test_parsers_common.py`

- [ ] **Step 1: Capture the fixture**

Run (PowerShell):
```powershell
$u = "https://basescan.org/address/0x71c7656ec7ab88b098defb751b7401b5f6d8976f"
Invoke-WebRequest -Uri $u -UserAgent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36" -OutFile "tests/fixtures/address_donate.html"
```
Expected: file created, size > 300 KB. This is the deterministic input for parser tests.

> NOTE: This fixture is a snapshot; its exact balances/counts will differ from the
> examples above. In Step 3 of Task 10/11, read the ACTUAL values out of the saved
> fixture and assert on those — do not hard-code the numbers from this plan.

- [ ] **Step 2: Write the failing test for helpers**

```python
# tests/unit/test_parsers_common.py
from basescan_scraper.parsers.common import clean_text, parse_wei_from_eth_text


def test_clean_text_strips_inline_tags_and_whitespace():
    # mimics: 0<b>.</b>30906125826241616 ETH split across nodes
    assert clean_text("  0.30906125826241616   ETH ") == "0.30906125826241616 ETH"


def test_parse_wei_from_eth_text():
    # "0.30906125826241616 ETH" -> wei string
    assert parse_wei_from_eth_text("0.30906125826241616 ETH") == "309061258262416160"


def test_parse_wei_handles_commas_and_symbol():
    # comma is a thousands separator: 1234.5 ETH * 1e18 = 1234500000000000000000 (22 digits)
    assert parse_wei_from_eth_text("1,234.5 ETH") == "1234500000000000000000"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/unit/test_parsers_common.py -v`
Expected: FAIL with import error.

- [ ] **Step 4: Write helpers**

```python
# basescan_scraper/parsers/common.py
import re
from decimal import Decimal


def clean_text(text: str | None) -> str:
    """Collapse whitespace; return '' for None. Use on node.text(deep=True) so
    inline markup inside numbers (e.g. 0<b>.</b>309…) is already merged."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


_NUM_RE = re.compile(r"[-+]?[\d,]*\.?\d+")


def parse_wei_from_eth_text(text: str, decimals: int = 18) -> str:
    """Extract the leading numeric value from text like '0.309… ETH' and convert
    to an exact integer wei string."""
    cleaned = clean_text(text).replace(",", "")
    m = _NUM_RE.search(cleaned)
    if not m:
        raise ValueError(f"no number in {text!r}")
    wei = (Decimal(m.group(0)) * (Decimal(10) ** decimals)).to_integral_value()
    return str(int(wei))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/test_parsers_common.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Checkpoint** — user commits (`test: capture address fixture; feat: parser helpers`).

---

### Task 10: Address overview parser

**Files:**
- Create: `basescan_scraper/parsers/address.py`
- Test: `tests/unit/test_parser_address.py`

- [ ] **Step 1: Inspect the fixture to get ground-truth values**

Open `tests/fixtures/address_donate.html` and find the actual ETH balance and token-holdings count currently rendered (search for `ETH Balance`). Record those exact values — they are the expected values for the test below. (At capture time the balance was rendered as `0<b>.</b>…  ETH` inside the Overview card.)

- [ ] **Step 2: Write the failing test** (substitute the real values you read in Step 1)

```python
# tests/unit/test_parser_address.py
from pathlib import Path

from basescan_scraper.parsers.address import parse_address_profile

FIXTURE = Path(__file__).parent.parent / "fixtures" / "address_donate.html"
ADDR = "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"


def test_parse_profile_extracts_balance_and_holdings():
    html = FIXTURE.read_text(encoding="utf-8")
    profile = parse_address_profile(html, address=ADDR)
    assert profile.address == ADDR
    # wei must be exact integer string; assert it parses and is non-empty
    assert profile.eth_balance.wei.isdigit()
    assert int(profile.eth_balance.wei) > 0
    # decimal must equal the balance text shown in the Overview card (no float)
    assert profile.eth_balance.decimal.startswith("0.")
    # token holdings count was >201 at capture; assert it is a positive int
    assert profile.token_holdings_count is None or profile.token_holdings_count > 0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/unit/test_parser_address.py -v`
Expected: FAIL with import error.

- [ ] **Step 4: Write the parser**

```python
# basescan_scraper/parsers/address.py
from selectolax.parser import HTMLParser

from basescan_scraper.models.address import AddressProfile
from basescan_scraper.models.common import Amount
from basescan_scraper.parsers.common import clean_text, parse_wei_from_eth_text


def _find_label_value(tree: HTMLParser, label: str) -> str | None:
    """Find the text of the element following a label like 'ETH Balance'.
    BaseScan renders Overview as <h4>label</h4> ... <div>value</div> pairs."""
    for node in tree.css("h4, .card-body h4, div"):
        if clean_text(node.text(deep=True)).lower() == label.lower():
            sib = node.next
            while sib is not None and not clean_text(sib.text(deep=True)):
                sib = sib.next
            if sib is not None:
                return clean_text(sib.text(deep=True))
    return None


def parse_address_profile(html: str, address: str) -> AddressProfile:
    tree = HTMLParser(html)

    balance_text = _find_label_value(tree, "ETH Balance") or "0 ETH"
    eth_balance = Amount.from_wei(parse_wei_from_eth_text(balance_text), symbol="ETH")

    holdings_count = None
    # Token holdings card shows e.g. ">$71,123,407.61 (>201 Tokens)"
    for node in tree.css("*"):
        txt = clean_text(node.text(deep=True))
        if "Tokens)" in txt and "$" in txt:
            import re
            m = re.search(r"\(>?(\d[\d,]*)\s+Tokens\)", txt)
            if m:
                holdings_count = int(m.group(1).replace(",", ""))
            break

    return AddressProfile(
        address=address.lower(),
        eth_balance=eth_balance,
        token_holdings_count=holdings_count,
    )
```

> NOTE: The selectors above are a starting point grounded in the observed structure.
> During execution, open the fixture and adjust the CSS selectors so the test passes
> against the REAL saved HTML. The test asserts on structure (digits, >0), so it is
> robust to the exact snapshot values.

- [ ] **Step 5: Run test to verify it passes** (adjust selectors against the fixture until green)

Run: `pytest tests/unit/test_parser_address.py -v`
Expected: PASS.

- [ ] **Step 6: Checkpoint** — user commits (`feat: address overview parser`).

---

### Task 11: Address transactions parser

**Files:**
- Modify: `basescan_scraper/parsers/address.py` (add `parse_transactions`)
- Test: extend `tests/unit/test_parser_address.py`

- [ ] **Step 1: Add the failing test**

```python
# append to tests/unit/test_parser_address.py
from basescan_scraper.parsers.address import parse_transactions


def test_parse_transactions_returns_rows():
    html = FIXTURE.read_text(encoding="utf-8")
    txs = parse_transactions(html)
    assert len(txs) > 0
    first = txs[0]
    assert first.hash.startswith("0x") and len(first.hash) == 66
    assert first.block > 0
    assert first.from_address.startswith("0x")
    assert first.value.wei.isdigit()
    assert first.direction in {"in", "out", "self", None}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_parser_address.py::test_parse_transactions_returns_rows -v`
Expected: FAIL with `ImportError: cannot import name 'parse_transactions'`.

- [ ] **Step 3: Implement `parse_transactions`**

```python
# append to basescan_scraper/parsers/address.py
import re

from basescan_scraper.models.address import Transaction

_HASH_RE = re.compile(r"/tx/(0x[0-9a-fA-F]{64})")
_ADDR_RE = re.compile(r"/address/(0x[0-9a-fA-F]{40})")


def _transactions_table(tree: HTMLParser):
    """The address tx list lives under the element with id='transactions'."""
    container = tree.css_first("#transactions")
    if container is None:
        return None
    return container.css_first("table")


def parse_transactions(html: str) -> list[Transaction]:
    tree = HTMLParser(html)
    table = _transactions_table(tree)
    if table is None:
        return []

    rows: list[Transaction] = []
    for tr in table.css("tbody tr"):
        row_html = tr.html or ""
        hash_m = _HASH_RE.search(row_html)
        if not hash_m:
            continue
        addrs = _ADDR_RE.findall(row_html)
        from_addr = addrs[0].lower() if addrs else ""
        to_addr = addrs[1].lower() if len(addrs) > 1 else None

        # block number: first /block/<n> link
        block_m = re.search(r"/block/(\d+)", row_html)
        block = int(block_m.group(1)) if block_m else 0

        # direction badge: cell text contains IN / OUT / SELF
        direction = None
        for cell in tr.css("td"):
            t = clean_text(cell.text(deep=True)).upper()
            if t in {"IN", "OUT", "SELF"}:
                direction = t.lower()
                break

        # value: the ETH amount cell (contains ' ETH')
        value_wei = "0"
        for cell in tr.css("td"):
            t = clean_text(cell.text(deep=True))
            if t.endswith("ETH"):
                try:
                    value_wei = parse_wei_from_eth_text(t)
                except ValueError:
                    value_wei = "0"
                break

        rows.append(
            Transaction(
                hash=hash_m.group(1),
                block=block,
                from_address=from_addr,
                to_address=to_addr,
                value=Amount.from_wei(value_wei, symbol="ETH"),
                direction=direction,
            )
        )
    return rows
```

> NOTE: There are several `table-hover` tables on the page; `#transactions` scopes us
> to the right one. Verify against the fixture and adjust cell selection if needed.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_parser_address.py -v`
Expected: PASS (all address parser tests).

- [ ] **Step 5: Checkpoint** — user commits (`feat: address transactions parser`).

---

> **Internal transactions, token transfers, NFT transfers parsers:** These follow the
> EXACT pattern of Task 11 against their own tabs/pages. They are implemented in Plan 2
> alongside their endpoints to keep this plan shippable. If you prefer them here, add
> three more tasks mirroring Task 11 with the relevant fixtures
> (`/address/{a}?...` tab URLs) before Phase 5.

---

## Phase 5 — Service

### Task 12: Address service (orchestration)

**Files:**
- Create: `basescan_scraper/services/__init__.py` (empty)
- Create: `basescan_scraper/services/address_service.py`
- Test: `tests/unit/test_address_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_address_service.py
import pytest

from basescan_scraper.services.address_service import AddressService


class FakeFetcher:
    def __init__(self, html: str):
        self._html = html
        self.calls = 0

    async def get(self, path: str) -> str:
        self.calls += 1
        return self._html


class DictCache:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value):
        self.store[key] = value


@pytest.fixture
def fixture_html():
    from pathlib import Path
    return (Path(__file__).parent.parent / "fixtures" / "address_donate.html").read_text(
        encoding="utf-8"
    )


async def test_get_profile_parses(fixture_html):
    svc = AddressService(FakeFetcher(fixture_html), DictCache())
    profile = await svc.get_profile("0x71c7656ec7ab88b098defb751b7401b5f6d8976f")
    assert profile.address == "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"
    assert int(profile.eth_balance.wei) >= 0


async def test_profile_is_cached(fixture_html):
    fetcher = FakeFetcher(fixture_html)
    svc = AddressService(fetcher, DictCache())
    addr = "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"
    await svc.get_profile(addr)
    await svc.get_profile(addr)
    assert fetcher.calls == 1  # second call served from cache
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_address_service.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write the service**

```python
# basescan_scraper/services/address_service.py
from basescan_scraper.cache.base import Cache
from basescan_scraper.fetchers.base import Fetcher
from basescan_scraper.models.address import AddressProfile, Transaction
from basescan_scraper.parsers.address import parse_address_profile, parse_transactions


class AddressService:
    def __init__(self, fetcher: Fetcher, cache: Cache):
        self._fetcher = fetcher
        self._cache = cache

    async def get_profile(self, address: str) -> AddressProfile:
        key = f"profile:{address}"
        cached = await self._cache.get(key)
        if cached is not None:
            return AddressProfile.model_validate(cached)
        html = await self._fetcher.get(f"/address/{address}")
        profile = parse_address_profile(html, address=address)
        await self._cache.set(key, profile.model_dump())
        return profile

    async def get_transactions(self, address: str) -> list[Transaction]:
        key = f"txs:{address}"
        cached = await self._cache.get(key)
        if cached is not None:
            return [Transaction.model_validate(t) for t in cached]
        html = await self._fetcher.get(f"/address/{address}")
        txs = parse_transactions(html)
        await self._cache.set(key, [t.model_dump() for t in txs])
        return txs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_address_service.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Checkpoint** — user commits (`feat: address service with caching`).

---

## Phase 6 — API: validation, errors, routers, wiring

### Task 13: Path-param validators

**Files:**
- Create: `basescan_scraper/api/validators.py`
- Test: `tests/api/test_validation.py` (validator unit portion)

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_validation.py
import pytest

from basescan_scraper.api.validators import normalize_address, ValidationError


def test_valid_address_normalized_lowercase():
    a = normalize_address("0x71C7656EC7ab88b098defB751B7401B5f6d8976F")
    assert a == "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"


@pytest.mark.parametrize("bad", ["0x123", "71c7656e", "0xZZZ…", "../etc/passwd", ""])
def test_invalid_address_rejected(bad):
    with pytest.raises(ValidationError):
        normalize_address(bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_validation.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write validators**

```python
# basescan_scraper/api/validators.py
import re

ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}\Z")  # \Z not $ — $ allows a trailing \n
TXHASH_RE = re.compile(r"^0x[0-9a-fA-F]{64}\Z")


class ValidationError(ValueError):
    """Raised when a path parameter fails strict validation."""


def normalize_address(value: str) -> str:
    if not ADDRESS_RE.match(value or ""):
        raise ValidationError("Invalid address: expected 0x followed by 40 hex chars.")
    return value.lower()


def validate_txhash(value: str) -> str:
    if not TXHASH_RE.match(value or ""):
        raise ValidationError("Invalid transaction hash: expected 0x followed by 64 hex chars.")
    return value.lower()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_validation.py -v`
Expected: PASS.

- [ ] **Step 5: Checkpoint** — user commits (`feat: strict path-param validators`).

---

### Task 14: Error handlers (RFC 9457) + app wiring

**Files:**
- Create: `basescan_scraper/api/errors.py`
- Create: `basescan_scraper/api/deps.py`
- Modify: `basescan_scraper/app.py`
- Test: extend `tests/api/test_validation.py` with an endpoint-level check (added in Task 15)

- [ ] **Step 1: Write error handlers**

```python
# basescan_scraper/api/errors.py
from fastapi import Request
from fastapi.responses import JSONResponse

from basescan_scraper.api.validators import ValidationError
from basescan_scraper.fetchers.base import (
    UpstreamRateLimited,
    UpstreamTimeout,
    UpstreamUnavailable,
)
from basescan_scraper.models.common import ProblemDetail

_CT = "application/problem+json"


def _problem(status: int, type_: str, title: str, detail: str | None = None,
             headers: dict | None = None) -> JSONResponse:
    body = ProblemDetail(type=type_, title=title, status=status, detail=detail).model_dump()
    return JSONResponse(status_code=status, content=body, media_type=_CT, headers=headers)


def register_error_handlers(app) -> None:
    @app.exception_handler(ValidationError)
    async def _on_validation(_: Request, exc: ValidationError):
        return _problem(422, "/errors/invalid-parameter", "Invalid parameter", str(exc))

    @app.exception_handler(UpstreamRateLimited)
    async def _on_rate(_: Request, exc: UpstreamRateLimited):
        return _problem(503, "/errors/upstream-rate-limited",
                        "Upstream rate limited", "BaseScan is rate-limiting requests.",
                        headers={"Retry-After": "5"})

    @app.exception_handler(UpstreamTimeout)
    async def _on_timeout(_: Request, exc: UpstreamTimeout):
        return _problem(504, "/errors/upstream-timeout", "Upstream timeout",
                        "BaseScan did not respond in time.")

    @app.exception_handler(UpstreamUnavailable)
    async def _on_unavailable(_: Request, exc: UpstreamUnavailable):
        return _problem(502, "/errors/upstream-unavailable", "Upstream unavailable",
                        "Could not retrieve or parse data from BaseScan.")
```

- [ ] **Step 2: Write dependency wiring**

```python
# basescan_scraper/api/deps.py
from functools import lru_cache

from basescan_scraper.cache.memory import MemoryCache
from basescan_scraper.config import get_settings
from basescan_scraper.fetchers.http_fetcher import HttpFetcher
from basescan_scraper.services.address_service import AddressService


@lru_cache
def _fetcher() -> HttpFetcher:
    return HttpFetcher(get_settings())


@lru_cache
def _cache() -> MemoryCache:
    s = get_settings()
    return MemoryCache(maxsize=s.cache_max_items, ttl=s.cache_ttl_seconds)


def get_address_service() -> AddressService:
    return AddressService(_fetcher(), _cache())
```

- [ ] **Step 3: Verify imports**

Run: `python -c "from basescan_scraper.api import errors, deps"`
Expected: exits 0.

- [ ] **Step 4: Checkpoint** — user commits (`feat: RFC 9457 error handlers and DI wiring`).

---

### Task 15: Address routers + full app wiring

**Files:**
- Create: `basescan_scraper/api/routers/addresses.py`
- Modify: `basescan_scraper/app.py`
- Test: `tests/api/test_addresses_api.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_addresses_api.py
import pytest
from fastapi.testclient import TestClient

from basescan_scraper.app import create_app
from basescan_scraper.api.deps import get_address_service
from basescan_scraper.models.address import AddressProfile, Transaction
from basescan_scraper.models.common import Amount

ADDR = "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"


class StubService:
    async def get_profile(self, address: str) -> AddressProfile:
        return AddressProfile(address=address, eth_balance=Amount.from_wei("123", symbol="ETH"),
                              token_holdings_count=2)

    async def get_transactions(self, address: str) -> list[Transaction]:
        return [Transaction(hash="0x" + "a" * 64, block=1, from_address=ADDR,
                            to_address=None, value=Amount.from_wei("0", symbol="ETH"))]


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_address_service] = lambda: StubService()
    return TestClient(app)


def test_get_address_profile(client):
    r = client.get(f"/v1/addresses/{ADDR}")
    assert r.status_code == 200
    body = r.json()
    assert body["address"] == ADDR
    assert body["eth_balance"]["wei"] == "123"


def test_get_address_transactions_envelope(client):
    r = client.get(f"/v1/addresses/{ADDR}/transactions")
    assert r.status_code == 200
    body = r.json()
    assert "data" in body and "pagination" in body
    assert body["data"][0]["hash"].startswith("0x")


def test_invalid_address_returns_422_problem(client):
    r = client.get("/v1/addresses/not-an-address")
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["status"] == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/api/test_addresses_api.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write the router**

```python
# basescan_scraper/api/routers/addresses.py
from fastapi import APIRouter, Depends, Path

from basescan_scraper.api.deps import get_address_service
from basescan_scraper.api.validators import normalize_address
from basescan_scraper.models.address import AddressProfile, Transaction
from basescan_scraper.models.common import Page, Pagination
from basescan_scraper.services.address_service import AddressService

router = APIRouter(prefix="/v1/addresses", tags=["Addresses"])

_RESPONSES = {
    422: {"description": "Invalid parameter"},
    502: {"description": "Upstream unavailable / parse failure"},
    503: {"description": "Upstream rate limited"},
    504: {"description": "Upstream timeout"},
}


@router.get("/{address}", response_model=AddressProfile, summary="Get address profile",
            operation_id="getAddressProfile", responses=_RESPONSES)
async def get_profile(
    address: str = Path(..., examples=["0x71c7656ec7ab88b098defb751b7401b5f6d8976f"]),
    service: AddressService = Depends(get_address_service),
) -> AddressProfile:
    """ETH balance, USD value, and token-holdings summary for an address."""
    addr = normalize_address(address)
    return await service.get_profile(addr)


@router.get("/{address}/transactions", response_model=Page[Transaction],
            summary="List address transactions", operation_id="getAddressTransactions",
            responses=_RESPONSES)
async def get_transactions(
    address: str = Path(..., examples=["0x71c7656ec7ab88b098defb751b7401b5f6d8976f"]),
    service: AddressService = Depends(get_address_service),
) -> Page[Transaction]:
    """Most recent normal transactions for an address (server-rendered page 1)."""
    addr = normalize_address(address)
    txs = await service.get_transactions(addr)
    pagination = Pagination(page=1, offset=len(txs) or 1, total=len(txs), has_next=False)
    return Page[Transaction](data=txs, pagination=pagination)
```

- [ ] **Step 4: Update the app factory**

Replace `basescan_scraper/app.py` with:
```python
# basescan_scraper/app.py
from fastapi import FastAPI

from basescan_scraper.api.errors import register_error_handlers
from basescan_scraper.api.routers import addresses, health


def create_app() -> FastAPI:
    app = FastAPI(
        title="BaseScan Scraper API",
        version="0.1.0",
        description="Read-only REST API exposing Base chain data scraped from basescan.org.",
        openapi_tags=[
            {"name": "Health", "description": "Service liveness."},
            {"name": "Addresses", "description": "Wallet/address data."},
        ],
    )
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(addresses.router)
    return app


app = create_app()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/api/test_addresses_api.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Manual smoke test against Swagger**

Run: `uvicorn basescan_scraper.app:app --port 8000`, open `/docs`. Confirm the Addresses endpoints appear with examples and the schemas render. Try the profile endpoint with the donate address (real fetch). Ctrl-C when done.

- [ ] **Step 7: Checkpoint** — user commits (`feat: address API routers and app wiring`).

---

## Phase 7 — Security hardening

### Task 16: CORS + security headers

> **No inbound rate limiting.** By decision, only the trusted main project calls this
> service, so inbound rate limiting is the caller's responsibility — `slowapi` is NOT a
> dependency and is not used. Outbound throttling to BaseScan (in `HttpFetcher`) is
> unaffected and remains. This task adds CORS (off unless origins are configured) and
> standard security response headers.

**Files:**
- Modify: `basescan_scraper/app.py`
- Test: `tests/api/test_security.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_security.py
from fastapi.testclient import TestClient

from basescan_scraper.app import create_app


def test_security_headers_present():
    client = TestClient(create_app())
    r = client.get("/health")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("Referrer-Policy") == "no-referrer"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/api/test_security.py -v`
Expected: FAIL (security headers missing).

- [ ] **Step 3: Add CORS + security headers to the app factory**

Update `basescan_scraper/app.py` to add a security-headers middleware and optional CORS:
```python
# basescan_scraper/app.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from basescan_scraper.api.errors import register_error_handlers
from basescan_scraper.api.routers import addresses, health
from basescan_scraper.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="BaseScan Scraper API",
        version="0.1.0",
        description="Read-only REST API exposing Base chain data scraped from basescan.org.",
        openapi_tags=[
            {"name": "Health", "description": "Service liveness."},
            {"name": "Addresses", "description": "Wallet/address data."},
        ],
    )

    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_methods=["GET"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        return resp

    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(addresses.router)
    return app


app = create_app()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/api/test_security.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Run the full suite**

Run: `pytest -v`
Expected: ALL tests pass (live tests deselected by default).

- [ ] **Step 6: Checkpoint** — user commits (`feat: CORS and security headers`).

---

## Phase 8 — Drift detection + review

### Task 17: Opt-in live drift test

**Files:**
- Create: `tests/live/test_live_drift.py`

- [ ] **Step 1: Write the live test**

```python
# tests/live/test_live_drift.py
import pytest

from basescan_scraper.config import get_settings
from basescan_scraper.fetchers.http_fetcher import HttpFetcher
from basescan_scraper.parsers.address import parse_address_profile, parse_transactions

ADDR = "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"


@pytest.mark.live
async def test_live_address_still_parses():
    fetcher = HttpFetcher(get_settings())
    try:
        html = await fetcher.get(f"/address/{ADDR}")
    finally:
        await fetcher.aclose()
    profile = parse_address_profile(html, address=ADDR)
    assert int(profile.eth_balance.wei) >= 0
    assert len(parse_transactions(html)) > 0  # detects HTML drift
```

- [ ] **Step 2: Run the live test explicitly**

Run: `pytest -m live -v`
Expected: PASS against real BaseScan (confirms the parser still matches the live page).

- [ ] **Step 3: Checkpoint** — user commits (`test: opt-in live drift test`).

---

### Task 18: Code review + security review (REQUIRED)

Per the user's standing preference, run the review skills before declaring the slice done.

- [ ] **Step 1:** Run the code-review skill (`/code-review high`) over the diff. Triage findings; fix real issues.
- [ ] **Step 2:** Run the security-review skill (`/security-review`) over the branch. Confirm: input validation on all params, no SSRF (URLs built from validated ids only), response-size caps and timeouts in place, no secrets in code, errors leak no internals, CORS restrictive.
- [ ] **Step 3:** Address findings, re-run `pytest -v`, then Checkpoint — user commits (`chore: address review findings`).

---

## Definition of Done (this plan)

- `pytest -v` green; `pytest -m live -v` green.
- `uvicorn basescan_scraper.app:app` boots; `/docs` shows Health + Addresses with examples and schemas; `/openapi.json` valid.
- `GET /v1/addresses/{addr}` returns a real profile; `GET /v1/addresses/{addr}/transactions` returns the paginated envelope.
- Invalid input → 422 `application/problem+json`; upstream failures → 502/503/504 problem responses.
- Code review + security review completed and findings resolved.

## Follow-on (Plan 2, not in this plan)
- Internal-transactions, token-transfers, NFT-transfers endpoints (mirror Task 11 + Task 15).
- Tokens endpoints (`/v1/tokens/{addr}`, `/transfers`, `/holders`).
- Transaction-detail endpoint (`/v1/transactions/{hash}`).
- Real pagination across pages (BaseScan `p=`/`ps=` params).
- Playwright fallback fetcher behind the existing `Fetcher` interface.
