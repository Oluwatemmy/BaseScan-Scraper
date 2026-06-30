# Plan 2b — Transaction Detail — Design Spec

**Date:** 2026-06-29
**Status:** Approved (pending final spec review)
**Builds on:** Plan 1 + Plan 2a (same layered architecture, `Fetcher`/`Cache`/parsers/services/API).

## 1. Purpose

Expose per-transaction detail so the bigger project can inspect a specific tx. Split
across composable endpoints so the core response stays lean while everything is reachable.

## 2. Key finding (verified)

The `/tx/{hash}` page is **server-rendered** — all fields are in the raw HTML (one fetch):
status, block, timestamp, from, to / contract-created, value, transaction fee, gas
price/limit/used, nonce, method/action, the **ERC-20 "Tokens Transferred"** section,
**input data**, and **event logs**. Confirmed on a token-transfer tx (rich) and a simple
ETH-transfer tx. No JS/JSON endpoint needed.

Parsing notes (from the captured fixtures):
- Tx-page timestamps use a **different format** than list pages: "Dec-14-2023 06:34:07 PM
  +UTC" (Mon-DD-YYYY hh:mm:ss AM/PM). A unix timestamp is also present in the page; the
  parser converts to ISO 8601 UTC (prefer the unix value if available).
- Value / Fee / Gas Price carry both ETH and USD ("0.0112… ETH $18.19") — extract the ETH
  part; ETH amounts use the exact-wei `Amount`.
- Block shows "47819759 Confirmed by Sequencer" — take the integer.
- `To:` is an address (+ optional nametag) for transfers, or "Interacted With (Contract)
  0x…" / a contract-creation marker for contract txs.

## 3. Scope

### In scope
- `GET /v1/transactions/{hash}` → `TransactionDetail` (core + ERC-20 token transfers + input).
- `GET /v1/transactions/{hash}/logs` → list of `EventLog`.
- Both parse slices of the same cached `/tx/{hash}` page.
- Models, a `TransactionService`, a `transactions` router, parsers, fixtures, tests,
  opt-in live drift, Playwright cross-check, code + security review.

### Out of scope (later)
- Internal-transactions-within-a-tx (mechanism unverified — may be JS-loaded; a separate
  follow-on once confirmed).
- Token endpoints (info/transfers/holders) — Plan 2c.
- Playwright fallback fetcher — still not needed.

## 4. API

`{hash}` is validated by the existing `validate_txhash` (`^0x[0-9a-fA-F]{64}\Z`) BEFORE any
URL is built (unchanged SSRF posture). Both endpoints fetch `/tx/{hash}`.

### `GET /v1/transactions/{hash}` → `TransactionDetail`
| Field | Type | Notes |
|-------|------|-------|
| `hash` | str | |
| `status` | str | "success" / "failed" |
| `block` | int | |
| `timestamp` | str\|null | ISO 8601 UTC |
| `from_address` | str | lowercased |
| `to_address` | str\|null | null for contract creation |
| `contract_created` | str\|null | set when the tx creates a contract |
| `value` | Amount | ETH (exact wei) |
| `transaction_fee` | Amount | ETH |
| `gas_price` | Amount | gwei (`Amount.from_wei(..., decimals=9, symbol="Gwei")`) |
| `gas_limit` | int | |
| `gas_used` | int | |
| `gas_used_pct` | str\|null | e.g. "47.5%" |
| `nonce` | int\|null | |
| `method` | str\|null | action/function name or 4-byte selector |
| `token_transfers` | list[TxTokenTransfer] | ERC-20 transfers inside the tx |
| `input` | InputData | |

`TxTokenTransfer`: `from_address`, `to_address`, `amount` (display str), `token_name`,
`token_symbol`, `token_address`. (Mirrors Plan 2a `TokenTransfer`; display-amount string.)

`InputData`: `method_id` (str\|null, the 4-byte selector), `decoded` (str\|null, the
function signature/name BaseScan shows), `raw_hex` (str).

### `GET /v1/transactions/{hash}/logs` → `{ "data": [EventLog] }`
`EventLog`: `log_index` (int\|null), `contract_address` (str), `topics` (list[str]),
`data` (str). Returned as a simple `{data: [...]}` list (logs aren't server-paginated).

## 5. Error handling

Same pattern as Plan 1/2a:
- Invalid hash → `422` problem+json (before any request).
- Tx not found (BaseScan renders a "Sorry, …" / search-not-found page with no tx overview)
  → `404` `/errors/not-found`.
- Required structure missing (drift) → `ParseError` → `502`.
- Upstream timeout/blocked/5xx → 504/503/502.

## 6. Models

New in `models/transaction.py` (kept separate from `models/address.py` for clarity):
`TransactionDetail`, `TxTokenTransfer`, `InputData`, `EventLog`. Reuse `Amount` from
`models/common.py`.

## 7. Parsers

New `parsers/transaction.py`:
- `parse_transaction_detail(html) -> TransactionDetail` — reads the label/value overview
  rows, the "Tokens Transferred" pills, and the input-data box. Add a tx-page timestamp
  helper (`_tx_timestamp`) for the "Mon-DD-YYYY hh:mm:ss AM/PM +UTC" / unix format.
  Reuse `parse_wei_from_eth_text` and `clean_text` from `parsers/common.py`.
- `parse_event_logs(html) -> list[EventLog]` — reads the Logs section.
- A `_tx_not_found(html) -> bool` guard (no overview / "not found" marker) → drives 404.

Fixtures (already captured): `tx_token.html` (contract tx with token transfers + logs),
`tx_eth.html` (simple ETH transfer). Parsers are written fixture-first with exact-value
assertions.

Verified ground-truth anchors:
- `tx_eth` (`0xb239798ab2…`): status "success", block 47819759,
  from `0x3ae6963e43f804e455b123c2015cfc88fdfe02b5`,
  to `0x71c7656ec7ab88b098defb751b7401b5f6d8976f`,
  value.decimal `0.011209138199984949`, fee.decimal `0.000000142838519275`,
  gas_price "0.00675" gwei, no token transfers.
- `tx_token` (`0xc5ac23d495…`): status "success", block 7894750,
  from `0x580d2c2da4f58d9efc2fdb5982ea67edc9620258`, value 0 ETH,
  has ERC-20 token transfers + event logs. (Exact transfer/log values read from the
  fixture during implementation.)

## 8. Service / DI

`TransactionService(fetcher, cache)`:
- `get_transaction(hash) -> TransactionDetail`
- `get_logs(hash) -> list[EventLog]`
Both fetch `/tx/{hash}` (cache key `tx:{hash}` for the raw page or per-method
`txdetail:{hash}` / `txlogs:{hash}` for parsed results), parse their slice. Wired via a new
`get_transaction_service` dependency and a `transactions` router included in the app.

## 9. Testing

- Parser unit tests vs `tx_token.html` / `tx_eth.html` (exact values: status, block,
  from/to, value/fee/gas, token-transfer row0, log count + log0).
- Not-found test using a captured `tx_notfound.html` fixture (a bogus hash page) → 404 path.
- Service tests with fake fetcher/cache.
- API tests (TestClient): both endpoints 200 + shape; invalid hash → 422 problem+json;
  not-found → 404 problem+json.
- Opt-in live drift test (real `/tx/{hash}` for both sample txns).
- Playwright cross-check of the API vs the live tx page; then code + security review.

## 10. Definition of done

- `GET /v1/transactions/{hash}` and `/logs` live; core + token transfers + input + logs
  correct against the live page.
- Invalid hash → 422; not-found → 404; drift → 502.
- Offline suite green; live drift green; ruff clean; cross-check clean; reviews done.
