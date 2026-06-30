# Plan 2c — Token Endpoints (Info + Holders) — Design Spec

**Date:** 2026-06-30
**Status:** Approved (pending final spec review)
**Builds on:** Plan 1 / 2a / 2b (same layered architecture; reuses `Page[T]`, `parse_pagination`, validators, error handlers).

## 1. Purpose

Expose token-level data the bigger project needs: a token's **info** (price, supply,
holders count, etc.) and its **holders** list. Both are server-rendered (plain httpx GET).

## 2. Scope

### In scope
- `GET /v1/tokens/{contract}` → `TokenInfo` (from `/token/{contract}`)
- `GET /v1/tokens/{contract}/holders` → `Page[TokenHolder]` (from
  `/token/generic-tokenholders2?a={contract}&p&ps`)
- New `models/token.py`, `parsers/token.py`, `TokenService`, `tokens` router, fixtures, tests.

### Out of scope
- **Token transfers (of a token) — Plan 2d.** Investigation showed a token's full transfer
  list is JS-rendered (loads into a `#transactions` iframe/spinner; `/tokentxns?contractAddress=`
  is NOT filtered to the token). Needs a browser network-capture to find its endpoint, like NFT.
  (Address-level token transfers already exist from Plan 2a.)
- Playwright fallback fetcher (still not needed for the in-scope endpoints).

## 3. Key findings (verified, server-rendered)

- **Token info** `/token/{contract}`: name/symbol/type from the `<title>`
  ("USDC (USDC) | ERC-20 | …"); price, onchain market cap, holders count in the page's
  meta/description text; "Max Total Supply N SYMBOL"; "Token Contract (WITH N Decimals)".
- **Token holders** `/token/generic-tokenholders2?a={contract}&p&ps`: a server-rendered
  table (the 4th table on the page, after 3 distribution-summary tables) with columns
  **Rank, Address, Label, Quantity, Percentage, Value**. The holder address is in the
  `/token/{contract}?a={holder}` link's `?a=` param. 50 rows/page; paginated via `&p&ps`
  (full navigation, no XHR). BaseScan lists only the **top 1,000 holders**
  ("Top 1,000 holders (From a total of 9,857,898 holders)").

## 4. API

`{contract}` is validated by the existing `normalize_address` (`^0x[0-9a-fA-F]{40}\Z`)
before any URL is built (unchanged SSRF posture).

### `GET /v1/tokens/{contract}` → `TokenInfo`
| Field | Type | Notes |
|-------|------|-------|
| `address` | str | lowercased |
| `name` | str\|null | from title |
| `symbol` | str\|null | from title |
| `type` | str\|null | "ERC-20" |
| `decimals` | int\|null | from "WITH N Decimals" |
| `price_usd` | str\|null | display, "$" stripped (e.g. "0.9996") |
| `max_total_supply` | str\|null | display (e.g. "4,207,496,819.876931") |
| `holders_count` | int\|null | e.g. 9858749 (the TRUE total holders) |
| `market_cap_usd` | str\|null | display, "$"/commas as-shown |

### `GET /v1/tokens/{contract}/holders` → `Page[TokenHolder]`
Query: `page` (≥1, default 1), `page_size` (1–100, default 50) — same validators as Plan 2a.
Maps to `/token/generic-tokenholders2?a={contract}&p={page}&ps={page_size}`.

`TokenHolder`: `rank` (int), `address` (str, lowercased — from the `/token/?a=` link),
`label` (str\|null — nametag, e.g. "Morpho: Morpho"), `quantity` (str display, e.g.
"195,270,620.9949"), `percentage` (str\|null — **computed** `quantity / total_supply * 100`
to 4 dp, e.g. "4.6410%"; BaseScan's server HTML carries only a JS "0.0000%" placeholder, so
the service computes it from `TokenInfo.max_total_supply`), `value_usd` (str\|null,
e.g. "195,195,051.26").

Pagination: `total_pages` from "Page X of Y"; `has_next = page < total_pages`. The list is
capped by BaseScan at the **top 1,000** holders, so `pagination.total` = 1000 (parsed from
"Top N holders"), independent of the true holder count (which is `TokenInfo.holders_count`).
A note in the schema documents the top-1000 cap.

## 5. Error handling

Same pattern: invalid contract or out-of-range page/page_size → `422` problem+json; a
non-token / not-found page (no token title/overview) → `404`; required structure missing
(drift) → `ParseError` → `502`; upstream failures → 502/503/504.

## 6. Models

New `models/token.py`: `TokenInfo`, `TokenHolder`. Reuse `Amount` only if needed (token
amounts are display strings here, like Plan 2a's TokenTransfer, since token decimals/price
vary — display strings are the honest representation).

## 7. Parsers

New `parsers/token.py`:
- `parse_token_info(html) -> TokenInfo` — title parse for name/symbol/type; regex/label
  reads for price, market cap, holders count, max supply, decimals. A `_token_not_found`
  guard (no token title / overview) drives 404.
- `parse_token_holders(html) -> (list[TokenHolder], total)` — locate the holders table
  (the table whose header contains "Quantity"/"Rank"); per row extract rank (1st cell),
  address (from the `/token/{contract}?a=…` link), label (the nametag text, if any),
  quantity, percentage, value. Total from "Top ([\d,]+) holders".
- Holders pagination uses the existing `parse_pagination` for "Page X of Y" (total_pages),
  combined with the top-N total above.

Fixtures (already captured): `token_usdc_info.html`, `token_holders_usdc.html` (USDC,
`0x833589fcd6edb6e08f4c7c32d4f71b54bda02913`).

**Verified ground-truth anchors:**
- TokenInfo (USDC): name "USDC", symbol "USDC", type "ERC-20", decimals 6,
  price_usd "0.9996", holders_count 9858749, max_total_supply "4,207,496,819.876931",
  market_cap_usd "4,205,868,518.61".
- TokenHolder row0: rank 1, address `0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb`,
  label "Morpho: Morpho", quantity "195,270,620.9949", percentage "4.6410%" (computed:
  195,270,620.9949 / 4,207,496,819.876931 × 100), value_usd "195,195,051.26"; 50 rows/page;
  total (list) 1000.

## 8. Service / DI

`TokenService(fetcher, cache)`:
- `get_info(address) -> TokenInfo` (cache `tokeninfo:{address}`)
- `get_holders(address, page, page_size) -> Page[TokenHolder]` (cache
  `tokenholders:{address}:{page}:{page_size}`)
Both fetch the relevant server-rendered page and parse it. New `get_token_service`
dependency + a `tokens` router included in the app.

## 9. Testing

- Parser unit tests vs the two fixtures with exact-value assertions (info fields; holder
  row0 + total + pagination).
- A not-found test (a bogus contract page) → 404 path.
- Service tests with fake fetcher/cache (paths carry `p`/`ps`; caching).
- API tests (TestClient): both endpoints 200 + shape; invalid contract → 422; page_size>100
  → 422; not-found → 404 (all problem+json).
- Opt-in live drift tests; Playwright cross-check; code + security review.

## 10. Definition of done

- `GET /v1/tokens/{contract}` and `/holders` live; correct against the live page.
- Invalid → 422; not-found → 404; drift → 502.
- Offline suite green; live drift green; ruff clean; cross-check clean; reviews done.
