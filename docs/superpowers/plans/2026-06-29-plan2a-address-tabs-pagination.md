# Plan 2a — Address Tabs + Real Pagination — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **COMMITS:** The user commits manually via GitHub Desktop. **Do NOT run `git commit`/`git push`/`git add`.** Where a task ends, pause for the user to commit.
> **VENV:** Use the venv interpreter for ALL commands: `.venv/Scripts/python.exe -m pytest …` and `.venv/Scripts/python.exe -m ruff check basescan_scraper tests`. Never bare `python`/`pytest`.
> **No `truststore` in the app** (user disables Avast). It may be installed in the venv for dev only; it is NOT in requirements.

**Goal:** Add three address activity lists (internal transactions, ERC-20 token transfers, NFT transfers), migrate the existing transactions endpoint to a paginated source, and give every list endpoint real `?page`/`?page_size` pagination with accurate totals.

**Architecture:** Extends Plan 1's layered design. Three tabs are server-rendered HTML (`/txs`, `/txsInternal`, `/tokentxns` with `&p&ps`); NFT is a JSON DataTables endpoint (`POST /nft-transfers.aspx/GetTableData_NftTransfers`). The `Fetcher` gains `post_json`. New parsers (HTML rows + NFT JSON + pagination metadata) feed page-aware `AddressService` methods returning the existing `Page[T]` envelope.

**Tech Stack:** Python 3.11+, FastAPI, httpx, selectolax, Pydantic v2, pytest, respx, ruff (all already present).

**Reference spec:** `docs/superpowers/specs/2026-06-29-plan2a-address-tabs-pagination-design.md`

**Fixtures already captured** in `tests/fixtures/` (real BaseScan data; do NOT re-download in tests):
- `txs_donate_p1.html` (total 96, "Page 1 of 2"), `txs_donate_p2.html` (page 2)
- `internal_donate.html` (total 8, "Page 1 of 1")
- `tokentxns_donate.html` (total 402, "Page 1 of 9")
- `nft_active.json` (the JSON response; `recordsTotal` 152, 25 rows) — address `0x7a63e8fc1d0a5e9be52f05817e8c49d9e2d6efae`
- (Plan 1's `address_donate.html` remains for the existing profile/tx tests.)

**Ground-truth first-row values** (verified — use as exact test assertions):
- `txs_donate_p1` row0: hash `0xb239798ab298435ae661f8693bdc9ba52c7f04bae796d7d99f1cb7d976e2140d`, block 47819759, method "Transfer", from `0x3ae6963e43f804e455b123c2015cfc88fdfe02b5`, to `0x71c7656ec7ab88b098defb751b7401b5f6d8976f`, direction "in", value decimal `0.011209138199984` (wei `11209138199984000`), fee decimal `0.00000014`, timestamp `2026-06-25T23:07:45Z`.
- `internal_donate` row0: parent_hash `0xb422713b8a582a9a524d7d0c0f6e68c61ed11f7d6433...` (full 64-hex), block 47793754, from `0x12eada5fb3d4e515cd095035ae006aeb36bf179e` (nuryale.base.eth), to `0x71c7656ec7ab88b098defb751b7401b5f6d8976f`, value decimal `0.00000073`, timestamp `2026-06-25T08:40:55Z` (note single-digit source hour "8").
- `tokentxns_donate` row0: hash `0xf15f81b97891035fed4859baba434393e06de13f5b47...`, block 47933577, from `0xbc37b1ba...`, to `0x71c7656ec7ab88b098defb751b7401b5f6d8976f`, amount `382,277`, token_name `Eos`, token_symbol `Eos`, token_address `0x69681a2c965fe656cdc19dc970f65cc6ef7e0269`, timestamp `2026-06-28T14:21:41Z`.
- `nft_active.json` row0: hash `0xfcb399511d2ebdf577be4bcdd3dc437898e3d2c86ef05f1b15eeffd503d92dbf`, block 46332875, from `0x7a63e8fc1d0a5e9be52f05817e8c49d9e2d6efae`, to `0x1c117e6cc629c414377fdbb427db329fd0821f9a`, token_type "ERC-1155", token_id `6277101738291256769055125632938578558371868663393442798971`, token_address `0x01df6fb6a28a89d6bfa53b2b3f20644abf417678`, collection_name `SuperPositions`, quantity `14526371714`, method "Exec Transaction", timestamp `2026-05-22T13:04:57Z`, recordsTotal 152.

---

## File Structure

```
basescan_scraper/
  models/address.py        # MODIFY: TokenTransfer.amount; NftTransfer +token_type/quantity/method
  parsers/common.py        # MODIFY: _DATE_RE/_row_timestamp accept single-digit hour (zero-pad)
  parsers/pagination.py    # CREATE: parse_pagination(html) -> (total, total_pages)
  parsers/address.py       # MODIFY: generalize table-finder; add parse_internal_transactions, parse_token_transfers
  parsers/nft.py           # CREATE: parse_nft_transfers(json_text) -> (list[NftTransfer], total)
  fetchers/base.py         # MODIFY: add post_json to Fetcher Protocol
  fetchers/http_fetcher.py # MODIFY: add post_json reusing the shared request loop
  services/address_service.py # MODIFY: _paginated_html, _paginated_nft, 4 page-aware methods
  api/validators.py        # MODIFY: add validate_page / validate_page_size
  api/routers/addresses.py # MODIFY: migrate transactions; add 3 endpoints (page/page_size)
tests/
  fixtures/ (already captured)
  unit/test_models_address.py     # MODIFY
  unit/test_parsers_common.py     # MODIFY (timestamp)
  unit/test_pagination_parser.py  # CREATE
  unit/test_parser_internal.py    # CREATE
  unit/test_parser_token.py       # CREATE
  unit/test_parser_nft.py         # CREATE
  unit/test_http_fetcher.py       # MODIFY (post_json)
  unit/test_address_service.py    # MODIFY (paginated methods)
  api/test_validation.py          # MODIFY (page/page_size)
  api/test_addresses_api.py       # MODIFY (new endpoints + pagination)
  live/test_live_drift.py         # MODIFY (4 endpoints)
```

---

## Phase 0 — Models & shared helpers

### Task 1: Model updates

**Files:** Modify `basescan_scraper/models/address.py`; Test `tests/unit/test_models_address.py`

- [ ] **Step 1: Add failing tests** (append to `tests/unit/test_models_address.py`)

```python
from basescan_scraper.models.address import InternalTransaction, NftTransfer, TokenTransfer


def test_token_transfer_amount_is_string():
    t = TokenTransfer(hash="0x" + "a" * 64, block=1, from_address="0x" + "1" * 40,
                      to_address="0x" + "2" * 40, amount="382,277",
                      token_name="Eos", token_symbol="Eos", token_address="0x" + "3" * 40)
    assert t.amount == "382,277"
    assert t.token_symbol == "Eos"


def test_nft_transfer_has_type_and_quantity():
    n = NftTransfer(hash="0x" + "a" * 64, block=1, from_address="0x" + "1" * 40,
                    to_address="0x" + "2" * 40, token_type="ERC-1155",
                    token_id="6277", token_address="0x" + "3" * 40,
                    collection_name="SuperPositions", quantity="14526371714", method="Exec Transaction")
    assert n.token_type == "ERC-1155"
    assert n.quantity == "14526371714"


def test_internal_transaction_shape():
    i = InternalTransaction(parent_hash="0x" + "a" * 64, block=1, from_address="0x" + "1" * 40,
                            to_address="0x" + "2" * 40, value=Amount.from_wei("730000000000", symbol="ETH"))
    assert i.parent_hash.startswith("0x")
```

- [ ] **Step 2: Run, expect FAIL**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_models_address.py -v`
Expected: FAIL (TokenTransfer has no `amount`; NftTransfer has no `token_type`).

- [ ] **Step 3: Edit `basescan_scraper/models/address.py`**

Replace the `TokenTransfer` class with:
```python
class TokenTransfer(BaseModel):
    hash: str
    block: int
    timestamp: Optional[str] = None
    from_address: str
    to_address: str
    amount: str = Field(examples=["382,277"], description="Display amount as shown by BaseScan")
    token_name: Optional[str] = None
    token_symbol: Optional[str] = None
    token_address: Optional[str] = None
```
Replace the `NftTransfer` class with:
```python
class NftTransfer(BaseModel):
    hash: str
    block: int
    timestamp: Optional[str] = None
    from_address: str
    to_address: str
    token_type: str = Field(examples=["ERC-721", "ERC-1155"])
    token_id: Optional[str] = None
    token_address: Optional[str] = None
    collection_name: Optional[str] = None
    quantity: Optional[str] = Field(default=None, description="Token count (ERC-1155)")
    method: Optional[str] = None
```
(`InternalTransaction` already exists with the needed fields — leave it.)

- [ ] **Step 4: Run, expect PASS**; then full suite `.venv/Scripts/python.exe -m pytest tests/ -q` and `.venv/Scripts/python.exe -m ruff check basescan_scraper tests`. Both clean.

- [ ] **Step 5: Checkpoint** — user commits (`feat: token/nft model fields for plan 2a`).

---

### Task 2: Timestamp helper handles single-digit hours

**Files:** Modify `basescan_scraper/parsers/common.py`; Test `tests/unit/test_parsers_common.py`

Context: `_row_timestamp` in `parsers/address.py` uses `_DATE_RE` from `common.py`-style logic with a two-digit hour. Real rows have single-digit hours ("2026-06-25 8:40:55"). Move the date-normalizer into `common.py` as a reusable function so both HTML and NFT parsers share it.

- [ ] **Step 1: Add failing tests** (append to `tests/unit/test_parsers_common.py`)

```python
from basescan_scraper.parsers.common import to_iso_utc


def test_to_iso_utc_two_digit_hour():
    assert to_iso_utc("2026-06-25 23:07:45") == "2026-06-25T23:07:45Z"


def test_to_iso_utc_single_digit_hour_is_zero_padded():
    assert to_iso_utc("2026-06-25 8:40:55") == "2026-06-25T08:40:55Z"


def test_to_iso_utc_bad_input_returns_none():
    assert to_iso_utc("not a date") is None
    assert to_iso_utc("") is None
    assert to_iso_utc(None) is None
```

- [ ] **Step 2: Run, expect FAIL** (no `to_iso_utc`).

- [ ] **Step 3: Add to `basescan_scraper/parsers/common.py`**

```python
_DATETIME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2}):(\d{2})$")


def to_iso_utc(text: str | None) -> str | None:
    """Convert 'YYYY-MM-DD H:MM:SS' (1- or 2-digit hour) to 'YYYY-MM-DDTHH:MM:SSZ'.
    Returns None if the text is empty or not a datetime."""
    m = _DATETIME_RE.match(clean_text(text))
    if not m:
        return None
    y, mo, d, h, mi, s = m.groups()
    return f"{y}-{mo}-{d}T{int(h):02d}:{mi}:{s}Z"
```

- [ ] **Step 4: Update `parsers/address.py` `_row_timestamp`** to use it. Replace the body of `_row_timestamp` with:
```python
def _row_timestamp(tr) -> str | None:
    """ISO 8601 UTC from the hidden showDate cell ('YYYY-MM-DD H:MM:SS')."""
    cell = tr.css_first("td.showDate")
    if cell is None:
        return None
    from basescan_scraper.parsers.common import to_iso_utc
    return to_iso_utc(clean_text(cell.text(deep=True)))
```
(Remove the now-unused `_DATE_RE` constant in `address.py` if nothing else uses it; run ruff to confirm.)

- [ ] **Step 5: Run** `.venv/Scripts/python.exe -m pytest tests/unit/test_parsers_common.py tests/unit/test_parser_address.py -v` — all PASS (existing address timestamp test `2026-06-25T23:07:45Z` still passes).

- [ ] **Step 6:** Full suite + ruff clean. **Checkpoint** — user commits (`fix: timestamp parser handles single-digit hours`).

---

## Phase 1 — Pagination parser

### Task 3: `parse_pagination`

**Files:** Create `basescan_scraper/parsers/pagination.py`; Test `tests/unit/test_pagination_parser.py`

- [ ] **Step 1: Create `tests/unit/test_pagination_parser.py`**

```python
from pathlib import Path

from basescan_scraper.parsers.pagination import parse_pagination

FX = Path(__file__).parent.parent / "fixtures"


def test_parse_pagination_txs_p1():
    html = (FX / "txs_donate_p1.html").read_text(encoding="utf-8")
    total, pages = parse_pagination(html)
    assert total == 96
    assert pages == 2


def test_parse_pagination_token():
    html = (FX / "tokentxns_donate.html").read_text(encoding="utf-8")
    total, pages = parse_pagination(html)
    assert total == 402
    assert pages == 9


def test_parse_pagination_absent_defaults():
    total, pages = parse_pagination("<html>nothing</html>")
    assert total is None
    assert pages == 1
```

- [ ] **Step 2: Run, expect FAIL** (import error).

- [ ] **Step 3: Create `basescan_scraper/parsers/pagination.py`**

```python
import re

_TOTAL_RE = re.compile(r"A total of ([\d,]+)")
_PAGES_RE = re.compile(r"Page \d+ of ([\d,]+)")


def parse_pagination(html: str) -> tuple[int | None, int]:
    """Return (total_items, total_pages) from a BaseScan list page.
    total_items is None if the 'A total of N' marker is absent; total_pages
    defaults to 1 if the 'Page X of Y' marker is absent."""
    tot_m = _TOTAL_RE.search(html)
    total = int(tot_m.group(1).replace(",", "")) if tot_m else None
    pg_m = _PAGES_RE.search(html)
    pages = int(pg_m.group(1).replace(",", "")) if pg_m else 1
    return total, pages
```

- [ ] **Step 4: Run, expect PASS**; full suite + ruff clean. **Checkpoint** — user commits (`feat: pagination metadata parser`).

---

## Phase 2 — HTML row parsers

### Task 4: Generalize transactions table-finder + verify on /txs

**Files:** Modify `basescan_scraper/parsers/address.py`; Test `tests/unit/test_parser_address.py`

Context: `_transactions_table` currently only finds `#transactions` (the `/address` page). The `/txs` page has no `#transactions` id. Generalize to prefer `#transactions`, else the first table containing a `/tx/` link.

- [ ] **Step 1: Add failing test** (append to `tests/unit/test_parser_address.py`)

```python
def test_parse_transactions_on_txs_page_full_precision():
    html = (FIXTURE.parent / "txs_donate_p1.html").read_text(encoding="utf-8")
    txs = parse_transactions(html)
    assert len(txs) == 50  # /txs default page size
    first = txs[0]
    assert first.hash == "0xb239798ab298435ae661f8693bdc9ba52c7f04bae796d7d99f1cb7d976e2140d"
    assert first.block == 47819759
    assert first.from_address == "0x3ae6963e43f804e455b123c2015cfc88fdfe02b5"
    assert first.to_address == "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"
    assert first.direction == "in"
    assert first.method == "Transfer"
    assert first.timestamp == "2026-06-25T23:07:45Z"
    # /txs shows fuller precision than the /address page
    assert first.value.decimal == "0.011209138199984"
    assert first.value.wei == "11209138199984000"
    assert first.txn_fee is not None and first.txn_fee.decimal == "0.00000014"
```

- [ ] **Step 2: Run, expect FAIL** (`_transactions_table` returns None → 0 rows).

- [ ] **Step 3: Edit `_transactions_table` in `parsers/address.py`**

```python
def _transactions_table(tree: HTMLParser):
    """Prefer the #transactions container (the /address page); otherwise the first
    table that contains a /tx/ link (the dedicated /txs list page)."""
    container = tree.css_first("#transactions")
    if container is not None:
        table = container.css_first("table")
        if table is not None:
            return table
    for table in tree.css("table"):
        if table.css_first("a[href^='/tx/']") is not None:
            return table
    return None
```

- [ ] **Step 4: Run** `.venv/Scripts/python.exe -m pytest tests/unit/test_parser_address.py -v` — ALL pass (existing `address_donate.html` tests still pass via the `#transactions` preference; new `/txs` test passes).

- [ ] **Step 5:** Full suite + ruff clean. **Checkpoint** — user commits (`feat: transactions parser works on /txs list page`).

---

### Task 5: Internal-transactions parser

**Files:** Modify `basescan_scraper/parsers/address.py`; Test `tests/unit/test_parser_internal.py`

Columns (verified): Block, Date(hidden), Age, Unix(hidden), Parent-Tx-Hash, Type, From, (arrow), To, Value. From/To resolve via `_row_addresses` (these rows carry `/address/` hrefs and/or `data-highlight-target`). Value is ETH via `span.td_showAmount` (text like "0.00000073 ETH").

- [ ] **Step 1: Create `tests/unit/test_parser_internal.py`**

```python
from pathlib import Path

from basescan_scraper.parsers.address import parse_internal_transactions

FX = Path(__file__).parent.parent / "fixtures"


def test_parse_internal_transactions():
    html = (FX / "internal_donate.html").read_text(encoding="utf-8")
    rows = parse_internal_transactions(html)
    assert len(rows) == 8
    r = rows[0]
    assert r.parent_hash.startswith("0xb422713b8a582a") and len(r.parent_hash) == 66
    assert r.block == 47793754
    assert r.from_address == "0x12eada5fb3d4e515cd095035ae006aeb36bf179e"   # nuryale.base.eth
    assert r.to_address == "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"     # donate
    assert r.timestamp == "2026-06-25T08:40:55Z"   # single-digit hour zero-padded
    assert r.value.decimal == "0.00000073"
```

- [ ] **Step 2: Run, expect FAIL** (no `parse_internal_transactions`).

- [ ] **Step 3: Add to `parsers/address.py`**

```python
from basescan_scraper.models.address import InternalTransaction  # add to existing imports


def parse_internal_transactions(html: str) -> list[InternalTransaction]:
    tree = HTMLParser(html)
    table = None
    for t in tree.css("table"):
        if t.css_first("a[href^='/tx/']") is not None:
            table = t
            break
    if table is None:
        return []
    rows: list[InternalTransaction] = []
    for tr in table.css("tbody tr"):
        row_html = tr.html or ""
        hash_m = _HASH_RE.search(row_html)
        if not hash_m:
            continue
        addrs = _row_addresses(tr)
        block_m = re.search(r"/block/(\d+)", row_html)
        value_wei = _row_value_wei(tr)
        rows.append(
            InternalTransaction(
                parent_hash=hash_m.group(1),
                block=int(block_m.group(1)) if block_m else 0,
                timestamp=_row_timestamp(tr),
                from_address=addrs[0] if addrs else "",
                to_address=addrs[1] if len(addrs) > 1 else None,
                value=Amount.from_wei(value_wei, symbol="ETH"),
            )
        )
    return rows
```

- [ ] **Step 4: Run** the internal test. If `to_address` is None (the donate "To" nametag), inspect the fixture row's To cell for its `data-highlight-target`/`/address/` href and confirm `_row_addresses` picks it up; the donate address must resolve. Adjust only if the real fixture shows a different structure. Expected: PASS.

- [ ] **Step 5:** Full suite + ruff clean. **Checkpoint** — user commits (`feat: internal transactions parser`).

---

### Task 6: Token-transfers parser

**Files:** Modify `basescan_scraper/parsers/address.py`; Test `tests/unit/test_parser_token.py`

Columns (verified): (preview), Hash, Method, MethodCustom, Block, Date, Age, Unix, From, IN/OUT, To, Amount, Token. Amount cell uses `span.td_showAmount` (display string e.g. "382,277", plus a hidden `td_showValue` USD). Token cell has `/token/0x…` href + text "ERC-20: Eos (Eos)".

- [ ] **Step 1: Create `tests/unit/test_parser_token.py`**

```python
from pathlib import Path

from basescan_scraper.parsers.address import parse_token_transfers

FX = Path(__file__).parent.parent / "fixtures"


def test_parse_token_transfers():
    html = (FX / "tokentxns_donate.html").read_text(encoding="utf-8")
    rows = parse_token_transfers(html)
    assert len(rows) == 50
    r = rows[0]
    assert r.hash.startswith("0xf15f81b9789103") and len(r.hash) == 66
    assert r.block == 47933577
    assert r.to_address == "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"
    assert r.amount == "382,277"
    assert r.token_address == "0x69681a2c965fe656cdc19dc970f65cc6ef7e0269"
    assert r.token_symbol == "Eos"
    assert r.token_name == "Eos"
    assert r.timestamp == "2026-06-28T14:21:41Z"
```

- [ ] **Step 2: Run, expect FAIL**.

- [ ] **Step 3: Add to `parsers/address.py`**

```python
from basescan_scraper.models.address import TokenTransfer  # add to existing imports

_TOKEN_HREF_RE = re.compile(r"/token/(0x[0-9a-fA-F]{40})")
# "ERC-20: Eos (Eos)" -> name "Eos", symbol "Eos"
_TOKEN_NAMESYM_RE = re.compile(r"ERC-\d+:\s*(.+?)\s*\(([^)]+)\)")


def _token_cell(tr):
    """The Token column: the <td> whose text contains 'ERC-'."""
    for td in tr.css("td"):
        if "ERC-" in clean_text(td.text(deep=True)):
            return td
    return None


def parse_token_transfers(html: str) -> list[TokenTransfer]:
    tree = HTMLParser(html)
    table = None
    for t in tree.css("table"):
        if t.css_first("a[href^='/tx/']") is not None:
            table = t
            break
    if table is None:
        return []
    rows: list[TokenTransfer] = []
    for tr in table.css("tbody tr"):
        row_html = tr.html or ""
        hash_m = _HASH_RE.search(row_html)
        if not hash_m:
            continue
        addrs = _row_addresses(tr)
        block_m = re.search(r"/block/(\d+)", row_html)
        amount_node = tr.css_first("span.td_showAmount")
        amount = clean_text(amount_node.text(deep=True)) if amount_node is not None else ""

        token_name = token_symbol = token_address = None
        tcell = _token_cell(tr)
        if tcell is not None:
            href_m = _TOKEN_HREF_RE.search(tcell.html or "")
            if href_m:
                token_address = href_m.group(1).lower()
            ns_m = _TOKEN_NAMESYM_RE.search(clean_text(tcell.text(deep=True)))
            if ns_m:
                token_name, token_symbol = ns_m.group(1), ns_m.group(2)

        # from/to: token rows put From first, To second (data-highlight-target order)
        rows.append(
            TokenTransfer(
                hash=hash_m.group(1),
                block=int(block_m.group(1)) if block_m else 0,
                timestamp=_row_timestamp(tr),
                from_address=addrs[0] if addrs else "",
                to_address=addrs[1] if len(addrs) > 1 else (addrs[0] if addrs else ""),
                amount=amount,
                token_name=token_name,
                token_symbol=token_symbol,
                token_address=token_address,
            )
        )
    return rows
```

> NOTE: `_row_addresses` may also pick up the token-contract `data-highlight-target` in the Token cell. Verify against the fixture that `addrs[0]`/`addrs[1]` are From/To (not the token). If the token contract appears among them, restrict address collection to the From/To cells (the cells before the Amount cell) — adjust and re-run until the test's `to_address` assertion passes.

- [ ] **Step 4: Run** the token test until PASS (make the from/to adjustment above only if needed).

- [ ] **Step 5:** Full suite + ruff clean. **Checkpoint** — user commits (`feat: token transfers parser`).

---

## Phase 3 — Fetcher.post_json + NFT JSON parser

### Task 7: `Fetcher.post_json`

**Files:** Modify `basescan_scraper/fetchers/base.py`, `basescan_scraper/fetchers/http_fetcher.py`; Test `tests/unit/test_http_fetcher.py`

- [ ] **Step 1: Add failing tests** (append to `tests/unit/test_http_fetcher.py`)

```python
@respx.mock
async def test_post_json_returns_text():
    route = respx.post(f"{BASE}/x.aspx/Get").mock(
        return_value=httpx.Response(200, json={"d": {"ok": 1}}))
    f = HttpFetcher(_settings())
    body = await f.post_json("/x.aspx/Get", {"a": 1})
    assert '"ok"' in body
    # sent as JSON with the right headers
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
```

- [ ] **Step 2: Run, expect FAIL** (no `post_json`).

- [ ] **Step 3: Add to `fetchers/base.py` `Fetcher` Protocol**

```python
    async def post_json(self, path: str, body: dict) -> str:
        """POST `body` as JSON and return the response text. Same retry/timeout/
        size-cap semantics as `get`. `path` is caller-validated."""
        ...
```

- [ ] **Step 4: Refactor `http_fetcher.py` to share the request loop**

Extract the existing retry/throttle/size-cap loop from `get` into a private
`_request(method, path, json_body=None)` and have both `get` and `post_json` call it:
```python
_JSON_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}


async def _request(self, method: str, path: str, json_body: dict | None = None) -> str:
    retries = self._settings.fetch_max_retries
    last_exc: Exception | None = None
    total_attempts = retries + 1
    for attempt in range(total_attempts):
        await self._wait_turn()
        try:
            if method == "POST":
                resp = await self._client.post(path, json=json_body, headers=_JSON_HEADERS)
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
```
(Keep `_HEADERS`, `__init__`, `_wait_turn`, `_backoff`, `aclose` as-is. The per-request
`_JSON_HEADERS` merge with the client's default headers.)

- [ ] **Step 5: Run** `.venv/Scripts/python.exe -m pytest tests/unit/test_http_fetcher.py -v` — all PASS (existing GET tests + 2 new POST tests).

- [ ] **Step 6:** Full suite + ruff clean. **Checkpoint** — user commits (`feat: Fetcher.post_json`).

---

### Task 8: NFT JSON parser

**Files:** Create `basescan_scraper/parsers/nft.py`; Test `tests/unit/test_parser_nft.py`

- [ ] **Step 1: Create `tests/unit/test_parser_nft.py`**

```python
from pathlib import Path

from basescan_scraper.parsers.nft import parse_nft_transfers

FX = Path(__file__).parent.parent / "fixtures"


def test_parse_nft_transfers():
    text = (FX / "nft_active.json").read_text(encoding="utf-8")
    rows, total = parse_nft_transfers(text)
    assert total == 152
    assert len(rows) == 25
    r = rows[0]
    assert r.hash == "0xfcb399511d2ebdf577be4bcdd3dc437898e3d2c86ef05f1b15eeffd503d92dbf"
    assert r.block == 46332875
    assert r.from_address == "0x7a63e8fc1d0a5e9be52f05817e8c49d9e2d6efae"
    assert r.to_address == "0x1c117e6cc629c414377fdbb427db329fd0821f9a"
    assert r.token_type == "ERC-1155"
    assert r.token_id == "6277101738291256769055125632938578558371868663393442798971"
    assert r.token_address == "0x01df6fb6a28a89d6bfa53b2b3f20644abf417678"
    assert r.collection_name == "SuperPositions"
    assert r.quantity == "14526371714"
    assert r.method == "Exec Transaction"
    assert r.timestamp == "2026-05-22T13:04:57Z"


def test_parse_nft_transfers_malformed_raises():
    import pytest

    from basescan_scraper.parsers.common import ParseError
    with pytest.raises(ParseError):
        parse_nft_transfers("not json")
```

- [ ] **Step 2: Run, expect FAIL**.

- [ ] **Step 3: Create `basescan_scraper/parsers/nft.py`**

```python
import json

from selectolax.parser import HTMLParser

from basescan_scraper.models.address import NftTransfer
from basescan_scraper.parsers.common import ParseError, clean_text, to_iso_utc


def _method_text(html_badge: str | None) -> str | None:
    if not html_badge:
        return None
    txt = clean_text(HTMLParser(html_badge).text(deep=True))
    return txt or None


def _collection(nft_name: str | None) -> str | None:
    if not nft_name:
        return None
    name = clean_text(nft_name)
    return name[len("NFT:"):].strip() if name.upper().startswith("NFT:") else name


def parse_nft_transfers(json_text: str) -> tuple[list[NftTransfer], int | None]:
    """Parse the GetTableData_NftTransfers response. Returns (rows, records_total)."""
    try:
        payload = json.loads(json_text)
        inner = payload["d"]
        if isinstance(inner, str):
            inner = json.loads(inner)
        records = inner["data"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ParseError(f"unexpected NFT response shape: {exc}") from exc

    total = inner.get("recordsTotal")
    rows: list[NftTransfer] = []
    for r in records:
        rows.append(
            NftTransfer(
                hash=r["txhash"],
                block=int(r["blockNumber"]),
                timestamp=to_iso_utc(r.get("dt")),
                from_address=(r.get("_from") or "").lower(),
                to_address=(r.get("_to") or "").lower(),
                token_type=f"ERC-{r.get('type')}" if r.get("type") else "",
                token_id=r.get("tokenId") or None,
                token_address=(r.get("tokenAddress") or "").lower() or None,
                collection_name=_collection(r.get("nftName")),
                quantity=r.get("value") or None,
                method=_method_text(r.get("txMethod")),
            )
        )
    return rows, total
```

- [ ] **Step 4: Run, expect PASS**; full suite + ruff clean. **Checkpoint** — user commits (`feat: NFT JSON parser`).

---

## Phase 4 — Service

### Task 9: Page-aware AddressService methods

**Files:** Modify `basescan_scraper/services/address_service.py`; Test `tests/unit/test_address_service.py`

- [ ] **Step 1: Add failing tests** (append to `tests/unit/test_address_service.py`)

```python
from pathlib import Path

from basescan_scraper.models.common import Page

FX = Path(__file__).parent.parent / "fixtures"


class PathFakeFetcher:
    """Returns fixture text based on the requested path/body; records calls."""
    def __init__(self):
        self.get_paths = []
        self.post_calls = []

    async def get(self, path: str) -> str:
        self.get_paths.append(path)
        if path.startswith("/txs?"):
            return (FX / "txs_donate_p1.html").read_text(encoding="utf-8")
        if path.startswith("/txsInternal?"):
            return (FX / "internal_donate.html").read_text(encoding="utf-8")
        if path.startswith("/tokentxns?"):
            return (FX / "tokentxns_donate.html").read_text(encoding="utf-8")
        return "<html></html>"

    async def post_json(self, path: str, body: dict) -> str:
        self.post_calls.append((path, body))
        return (FX / "nft_active.json").read_text(encoding="utf-8")


ADDR = "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"


async def test_transactions_paginated_envelope():
    svc = AddressService(PathFakeFetcher(), DictCache())
    page = await svc.get_transactions(ADDR, page=1, page_size=50)
    assert isinstance(page, Page)
    assert page.pagination.total == 96
    assert page.pagination.has_next is True       # page 1 of 2
    assert len(page.data) == 50


async def test_internal_and_token_and_nft():
    f = PathFakeFetcher()
    svc = AddressService(f, DictCache())
    internal = await svc.get_internal_transactions(ADDR, page=1, page_size=50)
    assert internal.pagination.total == 8 and len(internal.data) == 8
    token = await svc.get_token_transfers(ADDR, page=1, page_size=50)
    assert token.pagination.total == 402 and len(token.data) == 50
    nft = await svc.get_nft_transfers(ADDR, page=1, page_size=25)
    assert nft.pagination.total == 152 and len(nft.data) == 25
    # NFT uses post_json with start/length/Ext
    path, body = f.post_calls[0]
    assert path == "/nft-transfers.aspx/GetTableData_NftTransfers"
    assert body["dataTableModel"]["start"] == 0
    assert body["dataTableModel"]["length"] == 25
    assert body["dataTableModel"]["Ext"] == ADDR


async def test_paths_carry_page_and_size():
    f = PathFakeFetcher()
    svc = AddressService(f, DictCache())
    await svc.get_transactions(ADDR, page=2, page_size=50)
    assert any("/txs?a=" in p and "p=2" in p and "ps=50" in p for p in f.get_paths)
```

(Keep the existing `FakeFetcher`/`DictCache` from Plan 1's test file; `PathFakeFetcher` is additive. The existing `get_profile`/`get_transactions` non-paginated tests must be updated — see Step 4.)

- [ ] **Step 2: Run, expect FAIL**.

- [ ] **Step 3: Rewrite `basescan_scraper/services/address_service.py`**

```python
from basescan_scraper.cache.base import Cache
from basescan_scraper.fetchers.base import Fetcher
from basescan_scraper.models.address import (
    AddressProfile, InternalTransaction, NftTransfer, TokenTransfer, Transaction,
)
from basescan_scraper.models.common import Page, Pagination
from basescan_scraper.parsers.address import (
    parse_address_profile, parse_internal_transactions, parse_token_transfers,
    parse_transactions,
)
from basescan_scraper.parsers.nft import parse_nft_transfers
from basescan_scraper.parsers.pagination import parse_pagination

_NFT_PATH = "/nft-transfers.aspx/GetTableData_NftTransfers"
_NFT_COLUMNS = [
    {"data": d, "name": "", "searchable": True, "orderable": False,
     "search": {"value": "", "regex": False}}
    for d in ["preview", "txhash", "txMethod", "txMethodCustom", "blockNumber",
              "dt", "_from", "arrow", "_to", "type", "tokenAddress"]
]


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

    async def _paginated_html(self, list_path, address, page, page_size, row_parser, model):
        key = f"{list_path}:{address}:{page}:{page_size}"
        cached = await self._cache.get(key)
        if cached is not None:
            data = [model.model_validate(x) for x in cached["data"]]
            return Page(data=data, pagination=Pagination(**cached["pagination"]))
        html = await self._fetcher.get(f"/{list_path}?a={address}&p={page}&ps={page_size}")
        rows = row_parser(html)
        total, total_pages = parse_pagination(html)
        pagination = Pagination(page=page, offset=page_size, total=total,
                                has_next=page < total_pages)
        await self._cache.set(key, {"data": [r.model_dump() for r in rows],
                                    "pagination": pagination.model_dump()})
        return Page(data=rows, pagination=pagination)

    async def get_transactions(self, address: str, page: int = 1, page_size: int = 50) -> Page:
        return await self._paginated_html("txs", address, page, page_size,
                                          parse_transactions, Transaction)

    async def get_internal_transactions(self, address: str, page: int = 1, page_size: int = 50) -> Page:
        return await self._paginated_html("txsInternal", address, page, page_size,
                                          parse_internal_transactions, InternalTransaction)

    async def get_token_transfers(self, address: str, page: int = 1, page_size: int = 50) -> Page:
        return await self._paginated_html("tokentxns", address, page, page_size,
                                          parse_token_transfers, TokenTransfer)

    async def get_nft_transfers(self, address: str, page: int = 1, page_size: int = 25) -> Page:
        key = f"nft:{address}:{page}:{page_size}"
        cached = await self._cache.get(key)
        if cached is not None:
            data = [NftTransfer.model_validate(x) for x in cached["data"]]
            return Page(data=data, pagination=Pagination(**cached["pagination"]))
        body = {"dataTableModel": {
            "draw": 1, "columns": _NFT_COLUMNS, "order": [],
            "start": (page - 1) * page_size, "length": page_size,
            "search": {"value": "", "regex": False}, "Ext": address}}
        text = await self._fetcher.post_json(_NFT_PATH, body)
        rows, total = parse_nft_transfers(text)
        has_next = total is not None and page * page_size < total
        pagination = Pagination(page=page, offset=page_size, total=total, has_next=has_next)
        await self._cache.set(key, {"data": [r.model_dump() for r in rows],
                                    "pagination": pagination.model_dump()})
        return Page(data=rows, pagination=pagination)
```

- [ ] **Step 4: Update Plan 1's existing transactions service test.** In `tests/unit/test_address_service.py`, the old `test_get_transactions_parses_and_caches` called `get_transactions(addr)` expecting a `list`. Change it to expect a `Page` and pass `page=1, page_size=50`, OR delete it in favor of the new `test_transactions_paginated_envelope`. Update `test_profile_is_cached` only if affected (profile is unchanged). Run until all pass.

- [ ] **Step 5: Run** `.venv/Scripts/python.exe -m pytest tests/unit/test_address_service.py -v` — PASS; full suite + ruff clean. **Checkpoint** — user commits (`feat: page-aware address service methods`).

---

## Phase 5 — API

### Task 10: page / page_size validators

**Files:** Modify `basescan_scraper/api/validators.py`; Test `tests/api/test_validation.py`

- [ ] **Step 1: Add failing tests** (append to `tests/api/test_validation.py`)

```python
from basescan_scraper.api.validators import validate_page, validate_page_size


def test_validate_page_defaults_and_lower_bound():
    assert validate_page(None) == 1
    assert validate_page(3) == 3
    with pytest.raises(ValidationError):
        validate_page(0)


def test_validate_page_size_cap():
    assert validate_page_size(None) == 50
    assert validate_page_size(100) == 100
    with pytest.raises(ValidationError):
        validate_page_size(101)
    with pytest.raises(ValidationError):
        validate_page_size(0)
```

- [ ] **Step 2: Run, expect FAIL**.

- [ ] **Step 3: Add to `basescan_scraper/api/validators.py`**

```python
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 50


def validate_page(value: int | None) -> int:
    page = 1 if value is None else int(value)
    if page < 1:
        raise ValidationError("Invalid page: must be >= 1.")
    return page


def validate_page_size(value: int | None) -> int:
    size = DEFAULT_PAGE_SIZE if value is None else int(value)
    if size < 1 or size > MAX_PAGE_SIZE:
        raise ValidationError(f"Invalid page_size: must be 1..{MAX_PAGE_SIZE}.")
    return size
```

- [ ] **Step 4: Run, expect PASS**; full suite + ruff clean. **Checkpoint** — user commits (`feat: page/page_size validators`).

---

### Task 11: Routers — migrate transactions + 3 new endpoints

**Files:** Modify `basescan_scraper/api/routers/addresses.py`; Test `tests/api/test_addresses_api.py`

- [ ] **Step 1: Replace the stub service tests + add new endpoint tests** in `tests/api/test_addresses_api.py`

```python
import pytest
from fastapi.testclient import TestClient

from basescan_scraper.app import create_app
from basescan_scraper.api.deps import get_address_service
from basescan_scraper.models.address import (
    InternalTransaction, NftTransfer, TokenTransfer, Transaction,
)
from basescan_scraper.models.common import Amount, Page, Pagination

ADDR = "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"


def _page(items):
    return Page(data=items, pagination=Pagination(page=1, offset=50, total=len(items), has_next=False))


class StubService:
    async def get_profile(self, address):
        from basescan_scraper.models.address import AddressProfile
        return AddressProfile(address=address, eth_balance=Amount.from_wei("1", symbol="ETH"))

    async def get_transactions(self, address, page=1, page_size=50):
        return _page([Transaction(hash="0x" + "a" * 64, block=1, from_address=ADDR,
                                  to_address=None, value=Amount.from_wei("0", symbol="ETH"))])

    async def get_internal_transactions(self, address, page=1, page_size=50):
        return _page([InternalTransaction(parent_hash="0x" + "b" * 64, block=1,
                      from_address=ADDR, to_address=None, value=Amount.from_wei("0", symbol="ETH"))])

    async def get_token_transfers(self, address, page=1, page_size=50):
        return _page([TokenTransfer(hash="0x" + "c" * 64, block=1, from_address=ADDR,
                      to_address=ADDR, amount="123", token_symbol="X")])

    async def get_nft_transfers(self, address, page=1, page_size=25):
        return _page([NftTransfer(hash="0x" + "d" * 64, block=1, from_address=ADDR,
                      to_address=ADDR, token_type="ERC-721")])


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_address_service] = lambda: StubService()
    return TestClient(app)


@pytest.mark.parametrize("suffix", ["transactions", "internal-transactions",
                                    "token-transfers", "nft-transfers"])
def test_list_endpoints_envelope(client, suffix):
    r = client.get(f"/v1/addresses/{ADDR}/{suffix}")
    assert r.status_code == 200
    body = r.json()
    assert "data" in body and "pagination" in body
    assert body["data"][0]["hash"].startswith("0x")


def test_page_size_over_cap_422(client):
    r = client.get(f"/v1/addresses/{ADDR}/transactions?page_size=101")
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


def test_invalid_page_422(client):
    r = client.get(f"/v1/addresses/{ADDR}/transactions?page=0")
    assert r.status_code == 422
```

- [ ] **Step 2: Run, expect FAIL** (new endpoints 404; page validation absent).

- [ ] **Step 3: Rewrite `basescan_scraper/api/routers/addresses.py`**

```python
from fastapi import APIRouter, Depends, Path, Query

from basescan_scraper.api.deps import get_address_service
from basescan_scraper.api.validators import normalize_address, validate_page, validate_page_size
from basescan_scraper.models.address import (
    InternalTransaction, NftTransfer, TokenTransfer, Transaction,
)
from basescan_scraper.models.address import AddressProfile
from basescan_scraper.models.common import Page
from basescan_scraper.services.address_service import AddressService

router = APIRouter(prefix="/v1/addresses", tags=["Addresses"])

_RESPONSES = {
    422: {"description": "Invalid parameter"},
    502: {"description": "Upstream unavailable / parse failure"},
    503: {"description": "Upstream rate limited"},
    504: {"description": "Upstream timeout"},
}
# NOTE: no ge/le on the Query — bounds are enforced by validate_page/validate_page_size
# so that out-of-range values raise OUR ValidationError (rendered as problem+json),
# not FastAPI's default 422 shape. The description still documents the limits for Swagger.
_ADDR_PATH = Path(..., examples=["0x71c7656ec7ab88b098defb751b7401b5f6d8976f"])
_PAGE_Q = Query(default=None, description="1-based page number (>= 1)")
_SIZE_Q = Query(default=None, description="Items per page (1..100, default 50)")


@router.get("/{address}", response_model=AddressProfile, summary="Get address profile",
            operation_id="getAddressProfile", responses=_RESPONSES)
async def get_profile(address: str = _ADDR_PATH,
                      service: AddressService = Depends(get_address_service)) -> AddressProfile:
    """ETH balance, USD value, and token-holdings summary for an address."""
    return await service.get_profile(normalize_address(address))


@router.get("/{address}/transactions", response_model=Page[Transaction],
            summary="List address transactions", operation_id="getAddressTransactions",
            responses=_RESPONSES)
async def get_transactions(address: str = _ADDR_PATH, page: int = _PAGE_Q, page_size: int = _SIZE_Q,
                           service: AddressService = Depends(get_address_service)) -> Page[Transaction]:
    """Normal transactions for an address (paginated)."""
    return await service.get_transactions(normalize_address(address),
                                          validate_page(page), validate_page_size(page_size))


@router.get("/{address}/internal-transactions", response_model=Page[InternalTransaction],
            summary="List internal transactions", operation_id="getAddressInternalTransactions",
            responses=_RESPONSES)
async def get_internal(address: str = _ADDR_PATH, page: int = _PAGE_Q, page_size: int = _SIZE_Q,
                       service: AddressService = Depends(get_address_service)) -> Page[InternalTransaction]:
    """Contract-internal transactions involving an address (paginated)."""
    return await service.get_internal_transactions(normalize_address(address),
                                                   validate_page(page), validate_page_size(page_size))


@router.get("/{address}/token-transfers", response_model=Page[TokenTransfer],
            summary="List ERC-20 token transfers", operation_id="getAddressTokenTransfers",
            responses=_RESPONSES)
async def get_token_transfers(address: str = _ADDR_PATH, page: int = _PAGE_Q, page_size: int = _SIZE_Q,
                              service: AddressService = Depends(get_address_service)) -> Page[TokenTransfer]:
    """ERC-20 token transfers involving an address (paginated)."""
    return await service.get_token_transfers(normalize_address(address),
                                             validate_page(page), validate_page_size(page_size))


@router.get("/{address}/nft-transfers", response_model=Page[NftTransfer],
            summary="List NFT transfers", operation_id="getAddressNftTransfers",
            responses=_RESPONSES)
async def get_nft_transfers(address: str = _ADDR_PATH, page: int = _PAGE_Q, page_size: int = _SIZE_Q,
                            service: AddressService = Depends(get_address_service)) -> Page[NftTransfer]:
    """ERC-721/ERC-1155 NFT transfers involving an address (paginated)."""
    return await service.get_nft_transfers(normalize_address(address),
                                           validate_page(page), validate_page_size(page_size))
```

> NOTE: The `Query(...)` deliberately omits `ge`/`le` (see the comment above `_PAGE_Q`).
> If you add them, FastAPI returns its own 422 shape for out-of-range values BEFORE
> `validate_page_size` runs, breaking the RFC 9457 contract. Keep bounds in the validators
> and confirm `test_page_size_over_cap_422` sees `application/problem+json`.

- [ ] **Step 4: Run** `.venv/Scripts/python.exe -m pytest tests/api/test_addresses_api.py -v` — all PASS (adjust per the NOTE so the 422 is problem+json).

- [ ] **Step 5: Boot smoke test** — `.venv/Scripts/python.exe -m uvicorn basescan_scraper.app:app --port 8000`; open `/docs`, confirm 5 Addresses endpoints with `page`/`page_size` params; try `transactions` live for the donate address and confirm `pagination.total == 96`. Ctrl-C.

- [ ] **Step 6:** Full suite + ruff clean. **Checkpoint** — user commits (`feat: address list endpoints with pagination`).

---

## Phase 6 — Drift tests, cross-check, review

### Task 12: Opt-in live drift tests for the new endpoints

**Files:** Modify `tests/live/test_live_drift.py`

- [ ] **Step 1: Append live tests**

```python
@pytest.mark.live
async def test_live_internal_token_nft_parse():
    from basescan_scraper.services.address_service import AddressService
    from basescan_scraper.cache.memory import MemoryCache
    from basescan_scraper.fetchers.http_fetcher import HttpFetcher
    busy = "0x7a63e8fc1d0a5e9be52f05817e8c49d9e2d6efae"
    fetcher = HttpFetcher(get_settings())
    svc = AddressService(fetcher, MemoryCache(maxsize=10, ttl=0))
    try:
        txs = await svc.get_transactions(busy, page=1, page_size=50)
        nft = await svc.get_nft_transfers(busy, page=1, page_size=25)
    finally:
        await fetcher.aclose()
    assert txs.pagination.total and txs.pagination.total > 0
    assert nft.pagination.total and nft.pagination.total > 0
    assert all(t.hash.startswith("0x") for t in txs.data)
    assert all(n.token_type.startswith("ERC-") for n in nft.data)
```

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest -m live -v` — PASS against real BaseScan (needs Avast HTTPS scanning off). If a network/TLS error occurs, report it; do not weaken the test.

- [ ] **Step 3:** Full default suite green. **Checkpoint** — user commits (`test: live drift for plan 2a endpoints`).

---

### Task 13: Playwright cross-check + reviews (REQUIRED)

- [ ] **Step 1: Live Playwright cross-check** (MCP). Run the app; for the busy address compare API JSON vs the live page field-by-field for: token-transfers (first 2 rows: hash, from/to, amount, token), nft-transfers (first 2 rows: hash, type, token_id, collection, quantity, from/to), and transactions pagination (`total` matches "A total of N"). Note any mismatch and fix the parser.
- [ ] **Step 2:** Run `/code-review high` over the diff; fix real issues.
- [ ] **Step 3:** Run `/security-review`; confirm: page/page_size bounded before use; NFT body built only from the validated address (`Ext`); no SSRF; problem+json on all 422s; no secrets/leaks.
- [ ] **Step 4:** Address findings; re-run full suite + `-m live` + ruff. **Checkpoint** — user commits (`chore: address plan 2a review findings`).

---

## Definition of Done
- `GET /v1/addresses/{address}/{transactions|internal-transactions|token-transfers|nft-transfers}` all live with `?page`/`?page_size` (cap 100 → problem+json 422).
- `/transactions` migrated to `/txs?a=`; `pagination.total` accurate (96 for the donate address), paging works, fuller value precision.
- NFT via the JSON endpoint with `recordsTotal` totals.
- Offline suite green; `-m live` green; ruff clean; Playwright cross-check clean; code + security review done.

## Follow-on (later plans)
- Plan 2b: tokens endpoints + transaction-detail.
- Plan 2c: Playwright fallback fetcher (not needed for any Plan 2a endpoint).
