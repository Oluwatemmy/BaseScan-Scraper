# Plan 2a — Address Tabs + Real Pagination — Design Spec

**Date:** 2026-06-29
**Status:** Approved (pending final spec review)
**Builds on:** [`2026-06-28-basescan-scraper-design.md`](2026-06-28-basescan-scraper-design.md) (Plan 1)

## 1. Purpose

Plan 1 delivered the address profile and normal transactions (server-rendered page 1
only). Plan 2a rounds out **wallet profiles** by adding the remaining three address
activity lists, and introduces **real multi-page pagination** across all of them —
including retrofitting the existing transactions endpoint.

## 2. Key finding that drives this design

The **dedicated list pages are server-rendered, paginated, and expose the true totals**
in raw HTML (unlike the `/address/{addr}` page, where the total is JS-injected):

| Endpoint source | Rows/page | Raw-HTML total | Pager | Pagination params |
|-----------------|-----------|----------------|-------|-------------------|
| `/txs?a={addr}` (normal) | 50 (≤100) | "A total of N transactions found" | "Page X of Y" | `&p=N&ps=M` |
| `/txsInternal?a={addr}` | 50 | "A total of N internal transactions found" | "Page X of Y" | `&p=N&ps=M` |
| `/tokentxns?a={addr}` (ERC-20) | 50 | "A total of N txns found" | "Page X of Y" | `&p=N&ps=M` |
| `/tokentxns-nft?a={addr}` | 50 | (to confirm w/ fixture) | (to confirm) | `&p=N&ps=M` |

Verified live: `&p=2` returns page 2; `&ps=100` returns up to 100 rows/page and
collapses "Page 1 of 1" when all rows fit. All pages reuse the same Etherscan table
component, so the existing transaction parser works unchanged on `/txs?a=`.

### 2.1 NFT transfers: a JSON DataTables endpoint (not HTML)

NFT transfers are the exception. The page `/nft-transfers?a={addr}` ships an **empty
table shell**; rows are rendered client-side. Browser investigation (network capture)
revealed the data comes from a server **DataTables JSON endpoint**, which is callable
directly with httpx — **no browser, no cookies, no Cloudflare challenge** (verified):

- `POST https://basescan.org/nft-transfers.aspx/GetTableData_NftTransfers`
- Headers: `Content-Type: application/json`, `X-Requested-With: XMLHttpRequest`,
  `Accept: application/json`, `Referer: https://basescan.org/nft-transfers?a={addr}`, UA.
- Body: `{"dataTableModel":{"draw":1,"columns":[...],"order":[],"start":<offset>,`
  `"length":<page_size>,"search":{"value":"","regex":false},"Ext":"<address>"}}`
- Response: `{"d":{"draw","recordsTotal","recordsFiltered","data":[ {row…} ], …}}`
- Pagination: `start = (page-1)*page_size`, `length = page_size`; **`recordsTotal` is the
  true total** (verified 152; page 1 vs page 2 return different rows).
- Row fields (clean JSON): `txhash, blockNumber, dt` (e.g. "2025-10-25 3:21:01"),
  `_from, _to, type` ("1155"/"721"), `tokenId, tokenAddress, nftName`
  (e.g. "NFT: SuperPositions"), `value` (quantity), `txMethod` (an HTML badge —
  strip tags to get the method text), `_fromDisplay/_toDisplay` (nametag labels).
- The `start`/`length` are bounded by the same `page_size` cap (≤100). `length` > the
  server max simply returns fewer rows; we cap at 100 before sending.

This means NFT stays in **Approach A** (httpx), just via POST+JSON rather than GET+HTML.
The other three tabs remain GET+HTML.

## 3. Scope

### In scope
- **Migrate** `GET /v1/addresses/{address}/transactions` from the `/address` page to
  `/txs?a=` (gains accurate total + real paging; existing parser reused).
- **New** endpoints:
  - `GET /v1/addresses/{address}/internal-transactions` (GET HTML)
  - `GET /v1/addresses/{address}/token-transfers` (GET HTML)
  - `GET /v1/addresses/{address}/nft-transfers` (**POST JSON DataTables endpoint** — see §2.1)
- **Real pagination**: every list endpoint accepts `?page=N&page_size=M` and returns
  accurate `Pagination` (total, has_next, page count).
- A small **`Fetcher.post_json(path, body)`** addition (the NFT endpoint is a POST), plus
  an HTML parser per list page and a JSON parser for NFT; a pagination-metadata parser.
- Fixtures + tests (offline) and opt-in live drift tests per endpoint.

### Out of scope (later plans)
- Tokens endpoints (`/v1/tokens/...`) and transaction-detail (`/v1/transactions/{hash}`) — Plan 2b.
- Playwright fallback fetcher — Plan 2c. (NFT does NOT need it — see §2.1.)
- `truststore`/system-CA TLS handling — the user disables Avast HTTPS scanning instead;
  the app keeps httpx's default TLS and `truststore` is NOT an app dependency.
- Token `value` raw-precision (we use the displayed amount; see §6).

## 4. API

All list endpoints share the envelope and query params.

**Query params** (validated before any outbound request):
- `page`: integer ≥ 1, default 1.
- `page_size`: integer 1–100, default 50. Values > 100 are rejected with `422`
  (resource-safety cap) — not silently clamped.

**Request → upstream mapping:**
- HTML tabs (transactions, internal, token): GET `/{list}?a={address}&p={page}&ps={page_size}`
  where `{list}` ∈ `txs | txsInternal | tokentxns`.
- NFT: POST `/nft-transfers.aspx/GetTableData_NftTransfers` with the DataTables body from
  §2.1 (`start=(page-1)*page_size`, `length=page_size`, `Ext=address`).

The `address` is validated by the existing `normalize_address` before any URL/body is
built (unchanged SSRF posture). For NFT, `address` is only ever placed in the validated
`Ext` field / `Referer`, never used to choose a host.

**Response:** the existing `Page[T]` envelope:
```json
{ "data": [ ... ], "pagination": { "page": 2, "offset": 50, "total": 96, "has_next": false } }
```
- `total` = parsed "A total of N …" count.
- `has_next` = `page < total_pages` (from "Page X of Y"), with a fallback of
  `len(data) == page_size` if the pager text is absent.
- Requesting a page beyond the last returns `200` with `data: []` and `has_next: false`
  (BaseScan renders an empty table, not an error).

**Endpoints & response models**

| Path | Item model |
|------|-----------|
| `GET /v1/addresses/{address}/transactions` | `Transaction` (existing) |
| `GET /v1/addresses/{address}/internal-transactions` | `InternalTransaction` |
| `GET /v1/addresses/{address}/token-transfers` | `TokenTransfer` |
| `GET /v1/addresses/{address}/nft-transfers` | `NftTransfer` |

## 5. Parsers

A new `pagination.py` parser extracts, from any **HTML** list page:
- `total`: int from `r"A total of ([\d,]+) "`.
- `total_pages`: int from `r"Page \d+ of ([\d,]+)"` (default 1 if absent).

(NFT pagination metadata comes from the JSON `recordsTotal` instead — see the NFT bullet.)

Row parsers (each pure, fixture-tested; reuse `parsers/common.py` helpers and the
existing `_row_addresses`, `_row_timestamp`, `_row_value_wei`, `_row_method`):

- **Normal** (`/txs?a=`): reuse the existing `parse_transactions`, generalizing only the
  table-finder to **prefer `#transactions` if present (the `/address` page), else the
  first table containing a `/tx/` link** (the dedicated `/txs` page has no `#transactions`
  id). This keeps the existing `address_donate.html` fixture test passing while also
  working on `/txs?a=`.
- **Internal** (`/txsInternal?a=`): columns Block, Date, Parent-Tx-Hash, Type, From, To,
  Value. Fields: `parent_hash` (from the `/tx/` link), `block`, `timestamp`, `from_address`,
  `to_address` (via `_row_addresses` — these rows use `/address/` hrefs, no
  `data-highlight-target`), `value` (ETH `Amount` via `span.td_showAmount`). No fee/method.
- **Token** (`/tokentxns?a=`): columns Hash, Method, Block, Date, From, To, Amount, Token.
  Fields: `hash`, `block`, `timestamp`, `from_address`, `to_address`, `amount` (display
  string, see §6), `token_name`, `token_symbol`, `token_address` (from the Token cell's
  `/token/0x…` href / `data-highlight-target`). The Token cell is located by its
  `/token/` link (NOT by "ERC-" text): well-known tokens (e.g. USDC) render as
  "USDC (USDC)" with no "ERC-20:" prefix, so the prefix is optional when parsing
  name/symbol.
- **NFT** (JSON endpoint, §2.1): a `parse_nft_transfers(json_text) -> list[NftTransfer]`
  that loads the response, reads `d.data[]`, and maps each row:
  `hash`=`txhash`, `block`=`int(blockNumber)`, `timestamp`=ISO from `dt`
  ("YYYY-MM-DD H:MM:SS" → "YYYY-MM-DDTHH:MM:SSZ", zero-padding the hour),
  `from_address`=`_from.lower()`, `to_address`=`_to.lower()`, `token_type`=
  `"ERC-" + type` ("ERC-1155"/"ERC-721"), `token_id`=`tokenId`,
  `token_address`=`tokenAddress.lower()`, `collection_name`=`nftName` (strip a leading
  "NFT: "), `quantity`=`value` (string; meaningful for ERC-1155), `method`=text of the
  `txMethod` HTML badge (parse with selectolax / strip tags; None if empty). Pagination
  total comes from `d.recordsTotal`. The fixture is the **saved JSON response**
  (`nft_active.json`) captured from an NFT-active address during implementation.

## 6. Model adjustments

- `Transaction`, `InternalTransaction`: as defined in Plan 1 (confirm `InternalTransaction`
  has `parent_hash`, `block`, `timestamp`, `from_address`, `to_address`, `value`).
- `TokenTransfer.value` (currently `Amount`) → replaced by **`amount: str`** holding the
  display amount BaseScan shows (e.g. `"382,277"`), plus `token_name`, `token_symbol`,
  `token_address`. Rationale: the list page shows only the human-readable amount; raw
  value + token decimals are not present, so a display string is the honest, precise-as-
  available representation. ETH amounts elsewhere keep the exact wei `Amount`.
- `NftTransfer` (Plan 1 had `hash, block, timestamp, from_address, to_address, token_id,
  collection_name, token_address`) gains two fields from the JSON: **`token_type: str`**
  ("ERC-721"/"ERC-1155") and **`quantity: Optional[str]`** (token count, for ERC-1155),
  and **`method: Optional[str]`**. No `Amount` (NFTs have no ETH value on this row).

## 7. Fetcher, Service / DI

**Fetcher** gains one method alongside `get(path) -> str`:
`post_json(path, body: dict) -> str` — POSTs `body` as JSON with the NFT headers from
§2.1 and returns the response text. `HttpFetcher` implements it reusing the SAME retry /
timeout / size-cap / rate-limit logic as `get` (factor the shared request loop so both
paths share it). The Plan 1 `Fetcher` Protocol and `get` are unchanged.

**AddressService** gains page-aware list methods using two small helpers:
```
# HTML tabs (transactions, internal, token)
_paginated_html(list_path, address, page, page_size, row_parser) -> Page[T]:
    html = get(f"/{list_path}?a={address}&p={page}&ps={page_size}")
    rows = row_parser(html)
    total, total_pages = parse_pagination(html)
    return Page(rows, Pagination(page, page_size, total, page < total_pages))

# NFT (JSON DataTables endpoint)
_paginated_nft(address, page, page_size) -> Page[NftTransfer]:
    body = build_nft_body(address, start=(page-1)*page_size, length=page_size)
    text = post_json("/nft-transfers.aspx/GetTableData_NftTransfers", body)
    rows, total = parse_nft_transfers(text)            # parser returns (rows, recordsTotal)
    return Page(rows, Pagination(page, page_size, total, page*page_size < total))
```
Methods: `get_transactions` (migrated), `get_internal_transactions`,
`get_token_transfers`, `get_nft_transfers`. Cache key: `"{list}:{address}:{page}:{page_size}"`.

## 8. Error handling

Unchanged from Plan 1: invalid address or out-of-range `page_size` → `422`
`application/problem+json`; upstream failures → 502/503/504. Drift in a parser
(missing the expected list table on an HTML page that should have one, or the NFT JSON
not matching `{"d":{"data":[…]}}`) → `ParseError` → 502. An empty list (valid address,
no activity) is a normal `200` with `data: []` (HTML empty table / NFT `data: []`).

## 9. Testing

- **Parser unit tests** against saved fixtures: `txs_donate_p1.html`, `txs_donate_p2.html`,
  `internal_donate.html`, `tokentxns_donate.html` (HTML), and `nft_active.json` (the saved
  JSON response from an NFT-active address). Exact-value assertions on the first row of each
  (hash, block, from/to, amount/value, token fields; for NFT: token_type, token_id,
  token_address, collection_name, quantity).
- **Pagination tests**: HTML total + total_pages from real fixtures; NFT total from
  `recordsTotal`; page-2 fixture (`txs_donate_p2.html`) to assert `has_next` transitions and
  different rows.
- **Service tests** with fake fetcher/cache: correct upstream path built (`p`/`ps`),
  caching by page, envelope shape.
- **API tests** (TestClient): each endpoint 200 + envelope; `page_size` > 100 → 422;
  `page`/`page_size` non-integer → 422; invalid address → 422.
- **Opt-in live drift tests**: one per endpoint hitting real BaseScan.

## 10. Definition of done

- Four list endpoints live with `?page`/`?page_size`, accurate `total`/`has_next`.
- Existing `/transactions` migrated; its total is now accurate and paging works.
- All offline tests green; live drift tests green; ruff clean.
- Field-by-field Playwright cross-check of each new endpoint vs the live page (per the
  standing cross-check practice) once the Playwright MCP is reconnected.
- Code review + security review run and findings addressed.
