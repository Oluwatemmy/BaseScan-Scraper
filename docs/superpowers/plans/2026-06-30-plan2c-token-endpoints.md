# Plan 2c — Token Endpoints (Info + Holders) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

> **COMMITS:** User commits manually via GitHub Desktop. **Do NOT run git** (commit/add/push). Pause at task ends for the user to commit.
> **VENV:** Use the venv interpreter for ALL commands: `.venv/Scripts/python.exe -m pytest …`, `.venv/Scripts/python.exe -m ruff check basescan_scraper tests`. Never bare `python`/`pytest`.

**Goal:** Add `GET /v1/tokens/{contract}` (token info) and `GET /v1/tokens/{contract}/holders` (paginated holders), parsing the server-rendered `/token/{contract}` and `/token/generic-tokenholders2?a={contract}` pages.

**Architecture:** Extends Plan 1/2a/2b. New `models/token.py`, `parsers/token.py`, `TokenService`, and a `tokens` router. Holders reuse the `Page[T]` envelope and `parse_pagination`. Both are plain server-rendered httpx GETs.

**Tech Stack:** Python 3.11+, FastAPI, httpx, selectolax, Pydantic v2, pytest, ruff (all present).

**Reference spec:** `docs/superpowers/specs/2026-06-30-plan2c-token-endpoints-design.md`

**Fixtures already captured** in `tests/fixtures/` (real BaseScan; do NOT re-download in tests):
- `token_usdc_info.html` — `/token/{USDC}` info page
- `token_holders_usdc.html` — `/token/generic-tokenholders2?a={USDC}&p=1&ps=50` (50 holder rows)
- `token_notfound.html` — `/token/{EOA}` (a non-ERC-20 page: title "NFT | ERC-1155 …", no "Decimals)")
- (USDC contract = `0x833589fcd6edb6e08f4c7c32d4f71b54bda02913`)

**Verified ground-truth values** (assert these exactly against the fixtures):
- TokenInfo (USDC): name "USDC", symbol "USDC", type "ERC-20", decimals 6,
  price_usd "0.9996", market_cap_usd "4,205,868,518.61", holders_count 9858749,
  max_total_supply "4,207,496,819.876931", address `0x833589fcd6edb6e08f4c7c32d4f71b54bda02913`.
- TokenHolder row0: rank 1, address `0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb`,
  label "Morpho: Morpho", quantity "195,270,620.9949", percentage "0.0000%",
  value_usd "195,195,051.26" (strip the "$"). 50 rows/page; holders-list total 1000.

**Structural markers (verified):**
- Token name/symbol/type: the `<title>` "USDC (USDC) | ERC-20 | Address: … | BaseScan".
- price/market-cap/holders in the page meta text: `Price: $0.9996 | Onchain Market Cap: $4,205,868,518.61 | Holders: 9,858,749`.
- max supply: "Max Total Supply <value> USDC"; decimals: "Token Contract (WITH 6 Decimals)".
  (Read these from the cleaned text of the relevant element — the raw HTML has markup
  between the label and value, so a naive `WITH (\d+)` over raw HTML can miss; use
  `clean_text` of the element/section first.)
- Holders table: the table whose header row contains "Quantity" (the 4th table — after 3
  distribution-summary tables). Columns: Rank, Address, Label, Quantity, Percentage, Value.
  Holder address = the `?a=` param of the row's `/token/{contract}?a={holder}` link.
- Not-found (non-ERC-20) marker: a valid token page matches title `Name (SYM) | ERC-20`
  AND contains "Decimals)". The not-found fixture has neither — use that to drive 404.

---

## File Structure
```
basescan_scraper/
  models/token.py            # CREATE: TokenInfo, TokenHolder
  parsers/token.py           # CREATE: parse_token_info, parse_token_holders, is_token_not_found
  services/token_service.py  # CREATE: TokenService(get_info, get_holders)
  api/deps.py                # MODIFY: add get_token_service
  api/routers/tokens.py      # CREATE: 2 endpoints
  app.py                     # MODIFY: include tokens router
tests/
  unit/test_models_token.py      # CREATE
  unit/test_parser_token_info.py # CREATE
  unit/test_parser_token_holders.py # CREATE
  unit/test_token_service.py     # CREATE
  api/test_tokens_api.py         # CREATE
  live/test_live_drift.py        # MODIFY
```

---

## Task 1: Token models

**Files:** Create `basescan_scraper/models/token.py`; Test `tests/unit/test_models_token.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/unit/test_models_token.py
from basescan_scraper.models.token import TokenHolder, TokenInfo


def test_token_info_minimal():
    t = TokenInfo(address="0x" + "1" * 40)
    assert t.address.startswith("0x")
    assert t.name is None and t.decimals is None


def test_token_holder():
    h = TokenHolder(rank=1, address="0x" + "2" * 40, quantity="195,270,620.9949",
                    percentage="0.0000%")
    assert h.rank == 1
    assert h.label is None
```

- [ ] **Step 2: Run, expect FAIL** — `.venv/Scripts/python.exe -m pytest tests/unit/test_models_token.py -v`

- [ ] **Step 3: Create `basescan_scraper/models/token.py`**
```python
from typing import Optional

from pydantic import BaseModel, Field


class TokenInfo(BaseModel):
    address: str
    name: Optional[str] = None
    symbol: Optional[str] = None
    type: Optional[str] = Field(default=None, examples=["ERC-20"])
    decimals: Optional[int] = Field(default=None, examples=[6])
    price_usd: Optional[str] = Field(default=None, examples=["0.9996"])
    max_total_supply: Optional[str] = Field(default=None, examples=["4,207,496,819.876931"])
    holders_count: Optional[int] = Field(default=None, examples=[9858749])
    market_cap_usd: Optional[str] = Field(default=None, examples=["4,205,868,518.61"])


class TokenHolder(BaseModel):
    rank: int
    address: str
    label: Optional[str] = Field(default=None, examples=["Morpho: Morpho"])
    quantity: str = Field(examples=["195,270,620.9949"])
    percentage: str = Field(examples=["0.0000%"])
    value_usd: Optional[str] = Field(default=None, examples=["195,195,051.26"])
```

- [ ] **Step 4: Run, expect PASS**; full suite + ruff clean.
- [ ] **Step 5: Checkpoint** — user commits (`feat: token models`).

---

## Task 2: parse_token_info + not-found guard

**Files:** Create `basescan_scraper/parsers/token.py`; Test `tests/unit/test_parser_token_info.py`

- [ ] **Step 1: Write the failing tests**
```python
# tests/unit/test_parser_token_info.py
from pathlib import Path

import pytest

from basescan_scraper.parsers.common import ParseError
from basescan_scraper.parsers.token import is_token_not_found, parse_token_info

FX = Path(__file__).parent.parent / "fixtures"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"


def test_parse_token_info():
    html = (FX / "token_usdc_info.html").read_text(encoding="utf-8")
    t = parse_token_info(html, address=USDC)
    assert t.address == USDC
    assert t.name == "USDC"
    assert t.symbol == "USDC"
    assert t.type == "ERC-20"
    assert t.decimals == 6
    assert t.price_usd == "0.9996"
    assert t.market_cap_usd == "4,205,868,518.61"
    assert t.holders_count == 9858749
    assert t.max_total_supply == "4,207,496,819.876931"


def test_is_token_not_found():
    valid = (FX / "token_usdc_info.html").read_text(encoding="utf-8")
    missing = (FX / "token_notfound.html").read_text(encoding="utf-8")
    assert is_token_not_found(valid) is False
    assert is_token_not_found(missing) is True


def test_parse_token_info_raises_on_not_found():
    missing = (FX / "token_notfound.html").read_text(encoding="utf-8")
    with pytest.raises(ParseError):
        parse_token_info(missing, address="0x" + "1" * 40)
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Create `basescan_scraper/parsers/token.py`** (info part). Inspect the fixture to finalize the max-supply/decimals extraction so the EXACT ground-truth values match. Starting code:
```python
import re

from selectolax.parser import HTMLParser

from basescan_scraper.models.token import TokenHolder, TokenInfo
from basescan_scraper.parsers.common import ParseError, clean_text

_TITLE_RE = re.compile(r"(.+?)\s*\(([^)]+)\)\s*\|\s*(ERC-\d+)")
_PRICE_RE = re.compile(r"Price:\s*\$([\d.,]+)")
_MCAP_RE = re.compile(r"Onchain Market Cap:\s*\$([\d,]+\.?\d*)")
_HOLDERS_RE = re.compile(r"Holders:\s*([\d,]+)")
_MAXSUPPLY_RE = re.compile(r"Max Total Supply\s*([\d,]+\.?\d*)")
_DECIMALS_RE = re.compile(r"WITH\s*(\d+)\s*Decimals")


def is_token_not_found(html: str) -> bool:
    """A valid ERC-20 token page has a 'Name (SYM) | ERC-20' title AND a
    '(WITH N Decimals)' marker. The not-found / non-ERC-20 page has neither."""
    tree = HTMLParser(html)
    title_node = tree.css_first("title")
    title = clean_text(title_node.text(deep=True)) if title_node else ""
    return _TITLE_RE.match(title) is None or "Decimals)" not in html


def parse_token_info(html: str, address: str) -> TokenInfo:
    if is_token_not_found(html):
        raise ParseError("not a valid ERC-20 token page")
    tree = HTMLParser(html)
    title = clean_text(tree.css_first("title").text(deep=True))
    tm = _TITLE_RE.match(title)
    name = symbol = type_ = None
    if tm:
        name, symbol, type_ = tm.group(1), tm.group(2), tm.group(3)

    def _grp(rx):
        m = rx.search(html)
        return m.group(1) if m else None

    price = _grp(_PRICE_RE)
    mcap = _grp(_MCAP_RE)
    holders = _grp(_HOLDERS_RE)
    holders_count = int(holders.replace(",", "")) if holders else None
    # max supply / decimals: read from the cleaned page text (raw HTML has markup
    # between the label and value). Inspect the fixture and finalize these so the
    # ground-truth values (4,207,496,819.876931 and 6) match exactly.
    page_text = clean_text(tree.body.text(deep=True)) if tree.body else ""
    sup_m = _MAXSUPPLY_RE.search(page_text)
    max_supply = sup_m.group(1) if sup_m else None
    dec_m = _DECIMALS_RE.search(page_text)
    decimals = int(dec_m.group(1)) if dec_m else None

    return TokenInfo(
        address=address.lower(), name=name, symbol=symbol, type=type_,
        decimals=decimals, price_usd=price, max_total_supply=max_supply,
        holders_count=holders_count, market_cap_usd=mcap,
    )
```
> NOTE: Run the test and ITERATE the `_MAXSUPPLY_RE` / `_DECIMALS_RE` (and whether to
> search `html` vs `page_text`) until `max_total_supply == "4,207,496,819.876931"` and
> `decimals == 6`. Do not weaken the assertions.

- [ ] **Step 4: Run** until all 3 tests PASS (exact values).
- [ ] **Step 5:** Full suite + ruff clean. **Checkpoint** — user commits (`feat: token info parser`).

---

## Task 3: parse_token_holders

**Files:** Modify `basescan_scraper/parsers/token.py`; Test `tests/unit/test_parser_token_holders.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/unit/test_parser_token_holders.py
from pathlib import Path

from basescan_scraper.parsers.token import parse_token_holders

FX = Path(__file__).parent.parent / "fixtures"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"


def test_parse_token_holders():
    html = (FX / "token_holders_usdc.html").read_text(encoding="utf-8")
    holders, total = parse_token_holders(html, contract=USDC)
    assert total == 1000  # BaseScan lists only the top 1,000
    assert len(holders) == 50
    h = holders[0]
    assert h.rank == 1
    assert h.address == "0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb"
    assert h.label == "Morpho: Morpho"
    assert h.quantity == "195,270,620.9949"
    assert h.percentage == "0.0000%"
    assert h.value_usd == "195,195,051.26"
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Add to `basescan_scraper/parsers/token.py`**
```python
# Anchor to "(From a total of" — the page also says "Top 5 holders" / "Top 10 holders"
# in the distribution summary, so a bare "Top N holders" would wrongly match "Top 5".
# Allow the <span class='hidden-xs'> that sits between "holders" and "(From a total of"
# in the raw HTML. Verified to capture "1,000" on the fixture.
_TOP_RE = re.compile(r"Top ([\d,]+) holders\s*(?:<[^>]+>)?\s*\(?\s*From a total of")


def _holders_table(tree: HTMLParser):
    for t in tree.css("table"):
        heads = [clean_text(th.text(deep=True)) for th in t.css("thead th")]
        if "Quantity" in heads and "Rank" in heads:
            return t
    return None


def parse_token_holders(html: str, contract: str) -> tuple[list[TokenHolder], int | None]:
    tree = HTMLParser(html)
    table = _holders_table(tree)
    if table is None:
        return [], None
    addr_re = re.compile(rf"/token/{contract.lower()}\?a=(0x[0-9a-fA-F]{{40}})", re.I)
    holders: list[TokenHolder] = []
    for tr in table.css("tbody tr"):
        cells = tr.css("td")
        if len(cells) < 6:
            continue
        try:
            rank = int(clean_text(cells[0].text(deep=True)))
        except ValueError:
            continue
        am = addr_re.search(tr.html or "")
        address = am.group(1).lower() if am else ""
        # label: the nametag text in the Address cell (when not a bare 0x… address)
        label_text = clean_text(cells[1].text(deep=True)).replace("Copy Address", "").strip()
        label = label_text if (label_text and not label_text.lower().startswith("0x")) else None
        quantity = clean_text(cells[3].text(deep=True))
        percentage = clean_text(cells[4].text(deep=True)).split()[0] if clean_text(cells[4].text(deep=True)) else ""
        value_raw = clean_text(cells[5].text(deep=True))
        value_usd = value_raw.replace("$", "").strip() or None
        holders.append(TokenHolder(rank=rank, address=address, label=label,
                                   quantity=quantity, percentage=percentage, value_usd=value_usd))
    tot_m = _TOP_RE.search(html)
    total = int(tot_m.group(1).replace(",", "")) if tot_m else None
    return holders, total
```
> NOTE: Inspect the fixture's row 0 to confirm cell indices (rank=0, address/label=1,
> quantity=3, percentage=4, value=5 — there is an empty cell 2 for "Label" column in the
> markup). Adjust indices if the real fixture differs, so the ground-truth values match.
> The percentage cell may contain a progress bar after the number ("0.0000% 0") — take the
> first token. The label "Morpho: Morpho" is the nametag; a plain holder shows a truncated
> 0x address (→ label None).

- [ ] **Step 4: Run** until PASS (exact values; rank 1, Morpho label, quantity, percentage "0.0000%", value "195,195,051.26").
- [ ] **Step 5:** Full suite + ruff clean. **Checkpoint** — user commits (`feat: token holders parser`).

---

## Task 4: TokenService + DI

**Files:** Create `basescan_scraper/services/token_service.py`; Modify `basescan_scraper/api/deps.py`; Test `tests/unit/test_token_service.py`

- [ ] **Step 1: Write the failing tests**
```python
# tests/unit/test_token_service.py
from pathlib import Path

import pytest

from basescan_scraper.models.common import Page
from basescan_scraper.services.token_service import TokenService
from basescan_scraper.services.transaction_service import NotFound

FX = Path(__file__).parent.parent / "fixtures"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"


class PathFakeFetcher:
    def __init__(self):
        self.get_paths = []

    async def get(self, path: str) -> str:
        self.get_paths.append(path)
        if path.startswith("/token/generic-tokenholders2"):
            return (FX / "token_holders_usdc.html").read_text(encoding="utf-8")
        if path == f"/token/{USDC}":
            return (FX / "token_usdc_info.html").read_text(encoding="utf-8")
        return (FX / "token_notfound.html").read_text(encoding="utf-8")

    async def post_json(self, path, body):
        raise AssertionError("post_json not expected")


class DictCache:
    def __init__(self):
        self.store = {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v):
        self.store[k] = v


async def test_get_info_and_cache():
    f = PathFakeFetcher()
    svc = TokenService(f, DictCache())
    info = await svc.get_info(USDC)
    assert info.symbol == "USDC" and info.decimals == 6
    await svc.get_info(USDC)
    assert f.get_paths.count(f"/token/{USDC}") == 1  # cached


async def test_get_holders_paginated():
    f = PathFakeFetcher()
    svc = TokenService(f, DictCache())
    page = await svc.get_holders(USDC, page=2, page_size=50)
    assert isinstance(page, Page)
    assert page.pagination.total == 1000
    assert len(page.data) == 50
    assert any("generic-tokenholders2?a=" in p and "p=2" in p and "ps=50" in p
               for p in f.get_paths)


async def test_info_not_found_raises():
    svc = TokenService(PathFakeFetcher(), DictCache())
    with pytest.raises(NotFound):
        await svc.get_info("0x" + "9" * 40)
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Create `basescan_scraper/services/token_service.py`**
```python
from basescan_scraper.cache.base import Cache
from basescan_scraper.fetchers.base import Fetcher
from basescan_scraper.models.common import Page, Pagination
from basescan_scraper.models.token import TokenHolder, TokenInfo
from basescan_scraper.parsers.pagination import parse_pagination
from basescan_scraper.parsers.token import (
    is_token_not_found, parse_token_holders, parse_token_info,
)
from basescan_scraper.services.transaction_service import NotFound


class TokenService:
    def __init__(self, fetcher: Fetcher, cache: Cache):
        self._fetcher = fetcher
        self._cache = cache

    async def get_info(self, address: str) -> TokenInfo:
        key = f"tokeninfo:{address}"
        cached = await self._cache.get(key)
        if cached is not None:
            return TokenInfo.model_validate(cached)
        html = await self._fetcher.get(f"/token/{address}")
        if is_token_not_found(html):
            raise NotFound(address)
        info = parse_token_info(html, address=address)
        await self._cache.set(key, info.model_dump())
        return info

    async def get_holders(self, address: str, page: int = 1, page_size: int = 50) -> Page:
        key = f"tokenholders:{address}:{page}:{page_size}"
        cached = await self._cache.get(key)
        if cached is not None:
            data = [TokenHolder.model_validate(x) for x in cached["data"]]
            return Page(data=data, pagination=Pagination(**cached["pagination"]))
        html = await self._fetcher.get(
            f"/token/generic-tokenholders2?a={address}&p={page}&ps={page_size}")
        holders, total = parse_token_holders(html, contract=address)
        _, total_pages = parse_pagination(html)
        pagination = Pagination(page=page, offset=page_size, total=total,
                                has_next=page < total_pages)
        await self._cache.set(key, {"data": [h.model_dump() for h in holders],
                                    "pagination": pagination.model_dump()})
        return Page(data=holders, pagination=pagination)
```
(`NotFound` is reused from `transaction_service` — `errors.py` already maps it to 404.)

- [ ] **Step 4: Add to `basescan_scraper/api/deps.py`**
```python
from basescan_scraper.services.token_service import TokenService


def get_token_service() -> TokenService:
    return TokenService(_fetcher(), _cache())
```
(`_fetcher()` / `_cache()` already exist in deps.py.)

- [ ] **Step 5: Run** the service tests until PASS; full suite + ruff clean. **Checkpoint** — user commits (`feat: token service`).

---

## Task 5: tokens router (2 endpoints)

**Files:** Create `basescan_scraper/api/routers/tokens.py`; Modify `basescan_scraper/app.py`; Test `tests/api/test_tokens_api.py`

- [ ] **Step 1: Write the failing tests**
```python
# tests/api/test_tokens_api.py
import pytest
from fastapi.testclient import TestClient

from basescan_scraper.app import create_app
from basescan_scraper.api.deps import get_token_service
from basescan_scraper.models.common import Page, Pagination
from basescan_scraper.models.token import TokenHolder, TokenInfo
from basescan_scraper.services.transaction_service import NotFound

USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"


class StubService:
    async def get_info(self, address):
        return TokenInfo(address=address, name="USDC", symbol="USDC", type="ERC-20", decimals=6)

    async def get_holders(self, address, page=1, page_size=50):
        return Page(data=[TokenHolder(rank=1, address="0x" + "2" * 40, quantity="1", percentage="0%")],
                    pagination=Pagination(page=1, offset=50, total=1000, has_next=True))


class NotFoundService:
    async def get_info(self, address):
        raise NotFound(address)

    async def get_holders(self, address, page=1, page_size=50):
        raise NotFound(address)


def _client(service):
    app = create_app()
    app.dependency_overrides[get_token_service] = lambda: service
    return TestClient(app)


def test_get_token_info():
    r = _client(StubService()).get(f"/v1/tokens/{USDC}")
    assert r.status_code == 200
    assert r.json()["symbol"] == "USDC"


def test_get_token_holders_envelope():
    r = _client(StubService()).get(f"/v1/tokens/{USDC}/holders")
    assert r.status_code == 200
    body = r.json()
    assert body["pagination"]["total"] == 1000
    assert body["data"][0]["rank"] == 1


def test_invalid_contract_422():
    r = _client(StubService()).get("/v1/tokens/not-an-address")
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


def test_page_size_over_cap_422():
    r = _client(StubService()).get(f"/v1/tokens/{USDC}/holders?page_size=101")
    assert r.status_code == 422


def test_not_found_404():
    r = _client(NotFoundService()).get(f"/v1/tokens/{USDC}")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Create `basescan_scraper/api/routers/tokens.py`**
```python
from fastapi import APIRouter, Depends, Path, Query

from basescan_scraper.api.deps import get_token_service
from basescan_scraper.api.validators import normalize_address, validate_page, validate_page_size
from basescan_scraper.models.common import Page
from basescan_scraper.models.token import TokenHolder, TokenInfo
from basescan_scraper.services.token_service import TokenService

router = APIRouter(prefix="/v1/tokens", tags=["Tokens"])

_RESPONSES = {
    404: {"description": "Token not found"},
    422: {"description": "Invalid parameter"},
    502: {"description": "Upstream unavailable / parse failure"},
    503: {"description": "Upstream rate limited"},
    504: {"description": "Upstream timeout"},
}
_ADDR_PATH = Path(..., examples=["0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"])
_PAGE_Q = Query(default=None, description="1-based page number (>= 1)")
_SIZE_Q = Query(default=None, description="Items per page (1..100, default 50)")


@router.get("/{contract}", response_model=TokenInfo, summary="Get token info",
            operation_id="getTokenInfo", responses=_RESPONSES)
async def get_token_info(contract: str = _ADDR_PATH,
                         service: TokenService = Depends(get_token_service)) -> TokenInfo:
    """ERC-20 token info: name, symbol, decimals, price, supply, holders count, market cap."""
    return await service.get_info(normalize_address(contract))


@router.get("/{contract}/holders", response_model=Page[TokenHolder],
            summary="List token holders (top 1,000)", operation_id="getTokenHolders",
            responses=_RESPONSES)
async def get_token_holders(contract: str = _ADDR_PATH, page: int = _PAGE_Q,
                            page_size: int = _SIZE_Q,
                            service: TokenService = Depends(get_token_service)) -> Page[TokenHolder]:
    """Token holders, paginated. BaseScan lists only the top 1,000 holders."""
    return await service.get_holders(normalize_address(contract),
                                     validate_page(page), validate_page_size(page_size))
```

- [ ] **Step 4: Register in `basescan_scraper/app.py`** — add `tokens` to the `from basescan_scraper.api.routers import …` line, `app.include_router(tokens.router)`, and add `{"name": "Tokens", "description": "Token info and holders."}` to `openapi_tags`.

- [ ] **Step 5: Run** the API tests until PASS (confirm 422 and 404 are `application/problem+json`).
- [ ] **Step 6:** Full suite + ruff clean. **Boot smoke:** `.venv/Scripts/python.exe -c "from basescan_scraper.app import create_app; print(sorted(p for p in create_app().openapi()['paths'] if '/tokens' in p))"` — shows `/v1/tokens/{contract}` and `/v1/tokens/{contract}/holders`. **Checkpoint** — user commits (`feat: token info + holders endpoints`).

---

## Task 6: Live drift + cross-check + reviews

**Files:** Modify `tests/live/test_live_drift.py`

- [ ] **Step 1: Append a live test**
```python
@pytest.mark.live
async def test_live_token_info_and_holders():
    from basescan_scraper.services.token_service import TokenService
    from basescan_scraper.cache.memory import MemoryCache
    from basescan_scraper.fetchers.http_fetcher import HttpFetcher
    usdc = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
    fetcher = HttpFetcher(get_settings())
    svc = TokenService(fetcher, MemoryCache(maxsize=10, ttl=0))
    try:
        info = await svc.get_info(usdc)
        holders = await svc.get_holders(usdc, page=1, page_size=50)
    finally:
        await fetcher.aclose()
    assert info.symbol == "USDC" and info.decimals == 6
    assert info.holders_count and info.holders_count > 0
    assert len(holders.data) > 0
    assert all(h.address.startswith("0x") for h in holders.data)
    assert holders.pagination.total == 1000
```

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/ -q` (live excluded, count unchanged) and `.venv/Scripts/python.exe -m pytest -m live -v` (all live pass; retry once on transient network). ruff clean.
- [ ] **Step 3: Playwright cross-check** — run the app; compare the API JSON vs the live `/token/{USDC}` page (name/symbol/decimals/price/holders count) and the holders page (row 0 rank/address/quantity/percentage/value). Fix any mismatch.
- [ ] **Step 4:** Run `/code-review high` and `/security-review` over the diff; address findings (confirm: contract validated before fetch; page/page_size bounded; NotFound→404; no SSRF; problem+json on 422/404; no secrets/leaks). Re-run full suite + `-m live` + ruff.
- [ ] **Step 5: Checkpoint** — user commits (`test: live drift + review fixes for token endpoints`).

---

## Definition of Done
- `GET /v1/tokens/{contract}` returns token info; `/holders` returns the paginated top-1,000 holders.
- Invalid contract / page_size>100 → 422; non-token → 404; drift → 502.
- Offline suite green; `-m live` green; ruff clean; Playwright cross-check clean; code + security review done.

## Follow-on
- **Plan 2d: Token transfers (of a token)** — JS-rendered; capture its load mechanism with the browser first.
