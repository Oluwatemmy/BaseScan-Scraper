# Plan 2b — Transaction Detail — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

> **COMMITS:** User commits manually via GitHub Desktop. **Do NOT run git** (commit/add/push). Pause at task ends for the user to commit.
> **VENV:** Use the venv interpreter for ALL commands: `.venv/Scripts/python.exe -m pytest …`, `.venv/Scripts/python.exe -m ruff check basescan_scraper tests`. Never bare `python`/`pytest`.

**Goal:** Add `GET /v1/transactions/{hash}` (core details + ERC-20 token transfers + input data) and `GET /v1/transactions/{hash}/logs` (event logs), parsing the server-rendered `/tx/{hash}` page.

**Architecture:** Extends Plan 1/2a. One server-rendered fetch of `/tx/{hash}` (cached) feeds both endpoints; each parses its slice. New `models/transaction.py`, `parsers/transaction.py`, `TransactionService`, and a `transactions` router.

**Tech Stack:** Python 3.11+, FastAPI, httpx, selectolax, Pydantic v2, pytest, ruff (all present).

**Reference spec:** `docs/superpowers/specs/2026-06-29-plan2b-transaction-detail-design.md`

**Fixtures already captured** in `tests/fixtures/` (do NOT re-download in tests):
- `tx_eth.html` — simple ETH transfer `0xb239798ab298435ae661f8693bdc9ba52c7f04bae796d7d99f1cb7d976e2140d`
- `tx_token.html` — contract tx with ERC-20 transfers + logs `0xc5ac23d495c9fa1d1293ded109525ec865e382527b5bfe62a6970fbbf0418ca7`
- `tx_notfound.html` — a non-existent tx hash page (no `#spanTxHash`)

**Verified structural markers** (use these):
- `#spanTxHash` holds the tx hash; it is **absent on the not-found page** → that's the 404 signal.
- `#showUtcLocalDate` holds the timestamp text `"Jun-25-2026 11:07:45 PM +UTC"` (format `%b-%d-%Y %I:%M:%S %p`, UTC).
- From/To are `<a href="/address/0x…">` links (with optional nametag text).
- Overview fields render as label/value rows; value/fee/gas cells interleave HTML comments, so **locate values by inspecting the fixture** and assert the exact ground-truth values below.

**Ground-truth values** (assert these exactly):
- `tx_eth`: status "success", block 47819759, from `0x3ae6963e43f804e455b123c2015cfc88fdfe02b5`, to `0x71c7656ec7ab88b098defb751b7401b5f6d8976f`, value.decimal `0.011209138199984949`, transaction_fee.decimal `0.000000142838519275`, gas_price.decimal `0.00675` (gwei), nonce 3, timestamp `2026-06-25T23:07:45Z`, token_transfers == [].
- `tx_token`: status "success", block 7894750, from `0x580d2c2da4f58d9efc2fdb5982ea67edc9620258`, value.decimal "0", token_transfers length 2, has ≥1 event log.

---

## File Structure
```
basescan_scraper/
  models/transaction.py         # CREATE: TransactionDetail, TxTokenTransfer, InputData, EventLog
  parsers/transaction.py        # CREATE: parse_transaction_detail, parse_event_logs, helpers, not-found guard
  services/transaction_service.py # CREATE: TransactionService(get_transaction, get_logs)
  api/deps.py                   # MODIFY: add get_transaction_service
  api/errors.py                 # MODIFY: add NotFound -> 404 handler
  api/routers/transactions.py   # CREATE: 2 endpoints
  app.py                        # MODIFY: include transactions router
tests/
  unit/test_models_transaction.py   # CREATE
  unit/test_parser_transaction.py   # CREATE
  unit/test_transaction_service.py  # CREATE
  api/test_transactions_api.py      # CREATE
  live/test_live_drift.py           # MODIFY
```

---

## Task 1: Transaction models

**Files:** Create `basescan_scraper/models/transaction.py`; Test `tests/unit/test_models_transaction.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/unit/test_models_transaction.py
from basescan_scraper.models.common import Amount
from basescan_scraper.models.transaction import (
    EventLog, InputData, TransactionDetail, TxTokenTransfer,
)


def test_transaction_detail_minimal():
    tx = TransactionDetail(
        hash="0x" + "a" * 64, status="success", block=1, from_address="0x" + "1" * 40,
        value=Amount.from_wei("0", symbol="ETH"),
        transaction_fee=Amount.from_wei("0", symbol="ETH"),
        gas_price=Amount.from_wei("0", decimals=9, symbol="Gwei"),
        gas_limit=21000, gas_used=21000, input=InputData(raw_hex="0x"),
    )
    assert tx.status == "success"
    assert tx.to_address is None and tx.token_transfers == []


def test_tx_token_transfer_and_log():
    t = TxTokenTransfer(from_address="0x" + "1" * 40, to_address="0x" + "2" * 40,
                        amount="9", token_symbol="QUID", token_address="0x" + "3" * 40)
    assert t.amount == "9"
    log = EventLog(contract_address="0x" + "3" * 40, topics=["0xabc"], data="0x")
    assert log.topics == ["0xabc"]
```

- [ ] **Step 2: Run, expect FAIL** — `.venv/Scripts/python.exe -m pytest tests/unit/test_models_transaction.py -v`

- [ ] **Step 3: Create `basescan_scraper/models/transaction.py`**
```python
from typing import Optional

from pydantic import BaseModel, Field

from basescan_scraper.models.common import Amount


class TxTokenTransfer(BaseModel):
    from_address: str
    to_address: str
    amount: str = Field(examples=["382,277"], description="Display amount as shown by BaseScan")
    token_name: Optional[str] = None
    token_symbol: Optional[str] = None
    token_address: Optional[str] = None


class InputData(BaseModel):
    method_id: Optional[str] = Field(default=None, examples=["0xa9059cbb"])
    decoded: Optional[str] = Field(default=None, description="Function signature/name if shown")
    raw_hex: str = Field(examples=["0x"])


class EventLog(BaseModel):
    log_index: Optional[int] = None
    contract_address: str
    topics: list[str] = Field(default_factory=list)
    data: str = "0x"


class TransactionDetail(BaseModel):
    hash: str
    status: str = Field(examples=["success", "failed"])
    block: int
    timestamp: Optional[str] = Field(default=None, description="ISO 8601 UTC")
    from_address: str
    to_address: Optional[str] = Field(default=None, description="None for contract creation")
    contract_created: Optional[str] = None
    value: Amount
    transaction_fee: Amount
    gas_price: Amount
    gas_limit: int
    gas_used: int
    gas_used_pct: Optional[str] = None
    nonce: Optional[int] = None
    method: Optional[str] = None
    token_transfers: list[TxTokenTransfer] = Field(default_factory=list)
    input: InputData
```

- [ ] **Step 4: Run, expect PASS**; full suite + ruff clean.
- [ ] **Step 5: Checkpoint** — user commits (`feat: transaction-detail models`).

---

## Task 2: Parser helpers — tx timestamp + not-found guard

**Files:** Create `basescan_scraper/parsers/transaction.py` (start it here); Test `tests/unit/test_parser_transaction.py`

- [ ] **Step 1: Write the failing tests**
```python
# tests/unit/test_parser_transaction.py
from pathlib import Path

from basescan_scraper.parsers.transaction import is_tx_not_found, _tx_iso_timestamp

FX = Path(__file__).parent.parent / "fixtures"


def test_tx_iso_timestamp_parses_tx_page_format():
    assert _tx_iso_timestamp("Jun-25-2026 11:07:45 PM +UTC") == "2026-06-25T23:07:45Z"
    assert _tx_iso_timestamp("Dec-14-2023 06:34:07 PM +UTC") == "2023-12-14T18:34:07Z"
    assert _tx_iso_timestamp("nope") is None


def test_is_tx_not_found():
    assert is_tx_not_found((FX / "tx_notfound.html").read_text(encoding="utf-8")) is True
    assert is_tx_not_found((FX / "tx_eth.html").read_text(encoding="utf-8")) is False
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Create `basescan_scraper/parsers/transaction.py`** (initial)
```python
import re
from datetime import datetime, timezone

from selectolax.parser import HTMLParser

from basescan_scraper.parsers.common import clean_text

# tx page timestamp text: "Jun-25-2026 11:07:45 PM +UTC"
_TX_DT_RE = re.compile(r"([A-Z][a-z]{2}-\d{2}-\d{4} \d{1,2}:\d{2}:\d{2} [AP]M)")


def _tx_iso_timestamp(text: str | None) -> str | None:
    if not text:
        return None
    m = _TX_DT_RE.search(text)
    if not m:
        return None
    try:
        dt = datetime.strptime(m.group(1), "%b-%d-%Y %I:%M:%S %p").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def is_tx_not_found(html: str) -> bool:
    """A valid /tx page has #spanTxHash; the not-found page does not."""
    return HTMLParser(html).css_first("#spanTxHash") is None
```

- [ ] **Step 4: Run, expect PASS**; full suite + ruff clean.
- [ ] **Step 5: Checkpoint** — user commits (`feat: tx timestamp + not-found helpers`).

---

## Task 3: parse_transaction_detail — core overview + input data

**Files:** Modify `basescan_scraper/parsers/transaction.py`; Test `tests/unit/test_parser_transaction.py`

This is the fiddly part: locate each field by inspecting `tx_eth.html` and write selectors that produce the EXACT ground-truth values. The value/fee/gas cells contain interleaved HTML comments, so prefer scoping to the value `<span>` inside each labeled row.

- [ ] **Step 1: Add the failing test**
```python
# append to tests/unit/test_parser_transaction.py
from basescan_scraper.parsers.transaction import parse_transaction_detail


def test_parse_eth_tx_core():
    html = (FX / "tx_eth.html").read_text(encoding="utf-8")
    tx = parse_transaction_detail(html)
    assert tx.hash == "0xb239798ab298435ae661f8693bdc9ba52c7f04bae796d7d99f1cb7d976e2140d"
    assert tx.status == "success"
    assert tx.block == 47819759
    assert tx.timestamp == "2026-06-25T23:07:45Z"
    assert tx.from_address == "0x3ae6963e43f804e455b123c2015cfc88fdfe02b5"
    assert tx.to_address == "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"
    assert tx.value.decimal == "0.011209138199984949"
    assert tx.transaction_fee.decimal == "0.000000142838519275"
    assert tx.gas_price.decimal == "0.00675"
    assert tx.nonce == 3
    assert tx.token_transfers == []
    assert tx.input.raw_hex.startswith("0x")
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement `parse_transaction_detail`** (overview + input). Inspect `tx_eth.html` to finalize selectors; the function must produce the ground-truth values above. Suggested structure (reuse `parse_wei_from_eth_text` from `parsers/common.py` for ETH/gwei text):
```python
# add imports at top:
# from basescan_scraper.models.common import Amount
# from basescan_scraper.models.transaction import InputData, TransactionDetail, TxTokenTransfer
# from basescan_scraper.parsers.common import ParseError, parse_wei_from_eth_text

_HEX_ADDR_RE = re.compile(r"/address/(0x[0-9a-fA-F]{40})")


def _row_value_after_label(tree, label):
    """Find the labeled overview row and return its value-cell text. Inspect the
    fixture to confirm the row container/selector that yields the bare value."""
    for node in tree.css("div"):
        txt = clean_text(node.text(deep=True))
        if txt.startswith(label):
            return txt[len(label):].strip()
    return None


def parse_transaction_detail(html: str) -> TransactionDetail:
    tree = HTMLParser(html)
    hash_node = tree.css_first("#spanTxHash")
    if hash_node is None:
        raise ParseError("tx page missing #spanTxHash — possible drift")
    tx_hash = clean_text(hash_node.text(deep=True))

    # status: a badge with "Success"/"Fail". Inspect fixture for the exact node.
    status = "success" if "Success" in html else ("failed" if "Fail" in html else "unknown")

    # block: first /block/<n> link or the labeled row (strip "Confirmed by Sequencer")
    block_m = re.search(r"/block/(\d+)", html)
    block = int(block_m.group(1)) if block_m else 0

    # timestamp from #showUtcLocalDate
    ts_node = tree.css_first("#showUtcLocalDate")
    timestamp = _tx_iso_timestamp(clean_text(ts_node.text(deep=True))) if ts_node else None

    # from/to: the From row's /address/ link and the To row's /address/ link.
    # Inspect the fixture to scope to the correct rows (e.g. by row label) so the
    # FIRST link isn't a nametag for a different party. Produce the ground-truth
    # from/to. contract_created is set when the page shows a contract-creation marker.
    # value / fee / gas_price: read the ETH value from each labeled row's value span.
    # nonce / gas_limit / gas_used / gas_used_pct / method: from their rows.
    # input: the raw input hex (the Input Data textarea/box) + decoded method if shown.

    # ... finalize the above against tx_eth.html until the test passes ...
    return TransactionDetail(
        hash=tx_hash, status=status, block=block, timestamp=timestamp,
        from_address=from_address, to_address=to_address, contract_created=contract_created,
        value=value_amt, transaction_fee=fee_amt, gas_price=gas_price_amt,
        gas_limit=gas_limit, gas_used=gas_used, gas_used_pct=gas_used_pct,
        nonce=nonce, method=method, token_transfers=[], input=input_data,
    )
```
NOTE: The commented block is the discovery work — replace it with concrete extraction
that assigns every variable used in the return (`from_address`, `to_address`,
`contract_created`, `value_amt`, `fee_amt`, `gas_price_amt`, `gas_limit`, `gas_used`,
`gas_used_pct`, `nonce`, `method`, `input_data`) so the eth-tx test's exact values match.
Amount construction (mind the decimals — this is a correctness trap):
- ETH value/fee: `Amount.from_wei(parse_wei_from_eth_text(text), symbol="ETH")` (default 18 decimals).
- gas_price in **gwei**: `Amount.from_wei(parse_wei_from_eth_text(text, decimals=9), decimals=9, symbol="Gwei")`.
  Pass `decimals=9` to BOTH calls — otherwise "0.00675" gwei would be scaled by 1e18 and
  come out as "6750000". The test asserts `gas_price.decimal == "0.00675"`, which fails
  unless both use 9.
token_transfers is filled in Task 4 (leave `[]` here). `input_data` =
`InputData(method_id=…, decoded=…, raw_hex=…)` read from the Input Data box.

- [ ] **Step 4: Run** the eth-tx test, iterating selectors against the fixture until ALL asserted values match exactly.
- [ ] **Step 5:** Full suite + ruff clean. **Checkpoint** — user commits (`feat: transaction detail core parser`).

---

## Task 4: parse token transfers inside a tx

**Files:** Modify `basescan_scraper/parsers/transaction.py`; Test `tests/unit/test_parser_transaction.py`

- [ ] **Step 1: Add the failing test** (read exact row-0 values from `tx_token.html` first, then assert them)
```python
# append to tests/unit/test_parser_transaction.py
def test_parse_token_tx_transfers():
    html = (FX / "tx_token.html").read_text(encoding="utf-8")
    tx = parse_transaction_detail(html)
    assert tx.block == 7894750
    assert len(tx.token_transfers) == 2
    t0 = tx.token_transfers[0]
    assert t0.from_address.startswith("0x") and len(t0.from_address) == 42
    assert t0.to_address.startswith("0x") and len(t0.to_address) == 42
    assert t0.amount  # non-empty display amount
    assert t0.token_address and len(t0.token_address) == 42
```

- [ ] **Step 2: Run, expect FAIL** (token_transfers currently []).

- [ ] **Step 3: Add `_parse_tx_token_transfers(tree)`** and call it in `parse_transaction_detail` (replace the `token_transfers=[]`). The "Tokens Transferred" section renders each transfer as a row/pill containing From `/address/0x…`, To `/address/0x…`, an amount, and a token `/token/0x…` link with name (SYM). Inspect `tx_token.html` and extract per transfer: `from_address` (1st /address/), `to_address` (2nd /address/), `amount` (the displayed quantity), `token_address` (the /token/ link), `token_name`/`token_symbol` (reuse the same "ERC-20: Name (SYM)" / "Name (SYM)" logic as the Plan 2a token parser). Append `TxTokenTransfer`s.

- [ ] **Step 4: Run** until PASS (assert the real values you read from the fixture).
- [ ] **Step 5:** Full suite + ruff clean. **Checkpoint** — user commits (`feat: parse token transfers inside a tx`).

---

## Task 5: parse_event_logs

**Files:** Modify `basescan_scraper/parsers/transaction.py`; Test `tests/unit/test_parser_transaction.py`

- [ ] **Step 1: Add the failing test**
```python
# append to tests/unit/test_parser_transaction.py
from basescan_scraper.parsers.transaction import parse_event_logs


def test_parse_event_logs():
    html = (FX / "tx_token.html").read_text(encoding="utf-8")
    logs = parse_event_logs(html)
    assert len(logs) > 0
    log = logs[0]
    assert log.contract_address.startswith("0x") and len(log.contract_address) == 42
    assert isinstance(log.topics, list)


def test_parse_event_logs_eth_tx_minimal():
    # the simple ETH transfer has no event logs
    html = (FX / "tx_eth.html").read_text(encoding="utf-8")
    assert parse_event_logs(html) == []
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement `parse_event_logs(html) -> list[EventLog]`** in `parsers/transaction.py`. Inspect the Logs section of `tx_token.html`: each log block has a contract `/address/0x…`, an "Address" line, numbered "Topics" (topic0/1/2/3 — hex 0x… strings), and a "Data" block. Build `EventLog(log_index, contract_address, topics, data)` per block. If the section is absent (eth tx), return `[]`.

- [ ] **Step 4: Run** until PASS.
- [ ] **Step 5:** Full suite + ruff clean. **Checkpoint** — user commits (`feat: parse tx event logs`).

---

## Task 6: TransactionService + DI

**Files:** Create `basescan_scraper/services/transaction_service.py`; Modify `basescan_scraper/api/deps.py`; Test `tests/unit/test_transaction_service.py`

- [ ] **Step 1: Write the failing tests**
```python
# tests/unit/test_transaction_service.py
from pathlib import Path

import pytest

from basescan_scraper.parsers.common import ParseError
from basescan_scraper.services.transaction_service import NotFound, TransactionService

FX = Path(__file__).parent.parent / "fixtures"


class FakeFetcher:
    def __init__(self, name):
        self._html = (FX / name).read_text(encoding="utf-8")
        self.calls = 0

    async def get(self, path: str) -> str:
        self.calls += 1
        return self._html

    async def post_json(self, path, body):  # unused here
        raise AssertionError("post_json not expected")


class DictCache:
    def __init__(self):
        self.store = {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v):
        self.store[k] = v


async def test_get_transaction_parses_and_caches():
    f = FakeFetcher("tx_eth.html")
    svc = TransactionService(f, DictCache())
    h = "0xb239798ab298435ae661f8693bdc9ba52c7f04bae796d7d99f1cb7d976e2140d"
    tx = await svc.get_transaction(h)
    assert tx.block == 47819759
    await svc.get_transaction(h)
    assert f.calls == 1  # cached


async def test_get_logs():
    svc = TransactionService(FakeFetcher("tx_token.html"), DictCache())
    logs = await svc.get_logs("0x" + "c" * 64)
    assert len(logs) > 0


async def test_not_found_raises():
    svc = TransactionService(FakeFetcher("tx_notfound.html"), DictCache())
    with pytest.raises(NotFound):
        await svc.get_transaction("0x" + "9" * 64)
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Create `basescan_scraper/services/transaction_service.py`**
```python
from basescan_scraper.cache.base import Cache
from basescan_scraper.fetchers.base import Fetcher
from basescan_scraper.models.transaction import EventLog, TransactionDetail
from basescan_scraper.parsers.transaction import (
    is_tx_not_found, parse_event_logs, parse_transaction_detail,
)


class NotFound(Exception):
    """The requested transaction does not exist on BaseScan."""


class TransactionService:
    def __init__(self, fetcher: Fetcher, cache: Cache):
        self._fetcher = fetcher
        self._cache = cache

    async def _page(self, tx_hash: str) -> str:
        key = f"txpage:{tx_hash}"
        cached = await self._cache.get(key)
        if cached is not None:
            return cached
        html = await self._fetcher.get(f"/tx/{tx_hash}")
        if is_tx_not_found(html):
            raise NotFound(tx_hash)
        await self._cache.set(key, html)
        return html

    async def get_transaction(self, tx_hash: str) -> TransactionDetail:
        return parse_transaction_detail(await self._page(tx_hash))

    async def get_logs(self, tx_hash: str) -> list[EventLog]:
        return parse_event_logs(await self._page(tx_hash))
```
(Note: caches the raw page so both endpoints share one fetch. `NotFound` is checked before caching.)

- [ ] **Step 4: Add to `basescan_scraper/api/deps.py`**
```python
from basescan_scraper.services.transaction_service import TransactionService


def get_transaction_service() -> TransactionService:
    return TransactionService(_fetcher(), _cache())
```
(`_fetcher()` and `_cache()` already exist in deps.py from Plan 1.)

- [ ] **Step 5: Run** the service tests until PASS; full suite + ruff clean. **Checkpoint** — user commits (`feat: transaction service`).

---

## Task 7: API router (2 endpoints) + 404 handler

**Files:** Create `basescan_scraper/api/routers/transactions.py`; Modify `basescan_scraper/api/errors.py`, `basescan_scraper/app.py`; Test `tests/api/test_transactions_api.py`

- [ ] **Step 1: Write the failing tests**
```python
# tests/api/test_transactions_api.py
import pytest
from fastapi.testclient import TestClient

from basescan_scraper.app import create_app
from basescan_scraper.api.deps import get_transaction_service
from basescan_scraper.models.common import Amount
from basescan_scraper.models.transaction import EventLog, InputData, TransactionDetail
from basescan_scraper.services.transaction_service import NotFound

HASH = "0x" + "b" * 64


class StubService:
    async def get_transaction(self, tx_hash):
        return TransactionDetail(
            hash=tx_hash, status="success", block=1, from_address="0x" + "1" * 40,
            value=Amount.from_wei("0", symbol="ETH"),
            transaction_fee=Amount.from_wei("0", symbol="ETH"),
            gas_price=Amount.from_wei("0", decimals=9, symbol="Gwei"),
            gas_limit=21000, gas_used=21000, input=InputData(raw_hex="0x"))

    async def get_logs(self, tx_hash):
        return [EventLog(contract_address="0x" + "3" * 40, topics=["0xabc"], data="0x")]


class NotFoundService:
    async def get_transaction(self, tx_hash):
        raise NotFound(tx_hash)

    async def get_logs(self, tx_hash):
        raise NotFound(tx_hash)


def _client(service):
    app = create_app()
    app.dependency_overrides[get_transaction_service] = lambda: service
    return TestClient(app)


def test_get_transaction():
    r = _client(StubService()).get(f"/v1/transactions/{HASH}")
    assert r.status_code == 200
    assert r.json()["hash"] == HASH


def test_get_logs_envelope():
    r = _client(StubService()).get(f"/v1/transactions/{HASH}/logs")
    assert r.status_code == 200
    assert r.json()["data"][0]["contract_address"].startswith("0x")


def test_invalid_hash_422():
    r = _client(StubService()).get("/v1/transactions/0xnothex")
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


def test_not_found_404():
    r = _client(NotFoundService()).get(f"/v1/transactions/{HASH}")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Add a NotFound handler in `basescan_scraper/api/errors.py`** (use the existing `_problem` helper; import `NotFound`):
```python
from basescan_scraper.services.transaction_service import NotFound
...
    @app.exception_handler(NotFound)
    async def _on_not_found(_: Request, exc: NotFound):
        return _problem(404, "/errors/not-found", "Not found",
                        "No transaction found for that hash on Base.")
```
(Add inside `register_error_handlers`, alongside the existing handlers.)

- [ ] **Step 4: Create `basescan_scraper/api/routers/transactions.py`**
```python
from fastapi import APIRouter, Depends, Path

from basescan_scraper.api.deps import get_transaction_service
from basescan_scraper.api.validators import validate_txhash
from basescan_scraper.models.transaction import EventLog, TransactionDetail
from basescan_scraper.services.transaction_service import TransactionService

router = APIRouter(prefix="/v1/transactions", tags=["Transactions"])

_RESPONSES = {
    404: {"description": "Transaction not found"},
    422: {"description": "Invalid parameter"},
    502: {"description": "Upstream unavailable / parse failure"},
    503: {"description": "Upstream rate limited"},
    504: {"description": "Upstream timeout"},
}
_HASH_PATH = Path(..., examples=["0xb239798ab298435ae661f8693bdc9ba52c7f04bae796d7d99f1cb7d976e2140d"])


@router.get("/{tx_hash}", response_model=TransactionDetail, summary="Get transaction detail",
            operation_id="getTransaction", responses=_RESPONSES)
async def get_transaction(tx_hash: str = _HASH_PATH,
                          service: TransactionService = Depends(get_transaction_service)) -> TransactionDetail:
    """Core details + ERC-20 token transfers + input data for a transaction."""
    return await service.get_transaction(validate_txhash(tx_hash))


@router.get("/{tx_hash}/logs", summary="Get transaction event logs",
            operation_id="getTransactionLogs", responses=_RESPONSES)
async def get_logs(tx_hash: str = _HASH_PATH,
                   service: TransactionService = Depends(get_transaction_service)) -> dict:
    """Event logs emitted by the transaction."""
    logs: list[EventLog] = await service.get_logs(validate_txhash(tx_hash))
    return {"data": logs}
```

- [ ] **Step 5: Register the router in `basescan_scraper/app.py`** — add `from basescan_scraper.api.routers import transactions` and `app.include_router(transactions.router)`, and add `{"name": "Transactions", "description": "Transaction details and logs."}` to `openapi_tags`.

- [ ] **Step 6: Run** the API tests until PASS. Confirm `test_invalid_hash_422` and `test_not_found_404` return `application/problem+json`.
- [ ] **Step 7:** Full suite + ruff clean. **Boot smoke test:** `.venv/Scripts/python.exe -c "from basescan_scraper.app import create_app; print(sorted(p for p in create_app().openapi()['paths'] if 'transactions' in p))"` shows both paths. **Checkpoint** — user commits (`feat: transaction detail + logs endpoints`).

---

## Task 8: Live drift + cross-check + reviews

**Files:** Modify `tests/live/test_live_drift.py`

- [ ] **Step 1: Append a live test**
```python
@pytest.mark.live
async def test_live_transaction_detail_and_logs():
    from basescan_scraper.services.transaction_service import TransactionService
    from basescan_scraper.cache.memory import MemoryCache
    from basescan_scraper.fetchers.http_fetcher import HttpFetcher
    h = "0xb239798ab298435ae661f8693bdc9ba52c7f04bae796d7d99f1cb7d976e2140d"
    fetcher = HttpFetcher(get_settings())
    svc = TransactionService(fetcher, MemoryCache(maxsize=10, ttl=0))
    try:
        tx = await svc.get_transaction(h)
        logs = await svc.get_logs(h)
    finally:
        await fetcher.aclose()
    assert tx.hash == h and tx.block == 47819759 and tx.status == "success"
    assert isinstance(logs, list)
```

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/ -q` (default, live excluded — unchanged count) and `.venv/Scripts/python.exe -m pytest -m live -v` (all live pass). ruff clean.
- [ ] **Step 3: Playwright cross-check** — run the app; for a token tx, compare the API JSON vs the live `/tx` page: status, block, from/to, value, fee, gas, nonce, the token-transfer rows, and a couple of logs. Fix any mismatch.
- [ ] **Step 4:** Run `/code-review high` and `/security-review` over the diff; address findings (confirm: hash validated before fetch; NotFound→404; no SSRF; problem+json on 422/404; no secrets/leaks). Re-run full suite + `-m live` + ruff.
- [ ] **Step 5: Checkpoint** — user commits (`test: live drift + review fixes for tx detail`).

---

## Definition of Done
- `GET /v1/transactions/{hash}` returns core details + token transfers + input; `/logs` returns event logs.
- Invalid hash → 422 problem+json; not-found → 404 problem+json; drift → 502.
- Offline suite green; `-m live` green; ruff clean; Playwright cross-check clean; code + security review done.

## Follow-on
- Internal-transactions-within-a-tx (verify mechanism first — may be JS-loaded).
- Plan 2c: token endpoints (info / transfers / holders).
