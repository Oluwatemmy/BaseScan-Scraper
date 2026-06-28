# BaseScan Scraper — Design Spec

**Date:** 2026-06-28
**Status:** Approved (pending final spec review)

## 1. Purpose & Context

A scraper service that extracts on-chain data from [basescan.org](https://basescan.org)
(the Etherscan-family block explorer for the Base L2 chain) and exposes it to a
larger, not-yet-built project through a **REST API**.

The larger project will consume wallet/address profiles, token data, transaction
details, and (later) continuous monitoring. The scraper is deliberately built to
**not depend on the official Etherscan/BaseScan API** — the goal is a self-contained,
fast scraper so the bigger project is free of API keys, rate caps, and potential API
costs. The architecture keeps the data-source swappable so an API path *could* be
reintroduced per-endpoint later without rework, but that is not a goal of this build.

### Key finding from exploration
BaseScan's core data tables (transactions, token transfers, balances, holdings) are
**server-rendered in the page HTML** — they are present in the raw response, not
loaded by client-side JavaScript. This makes a lightweight HTTP+parse approach viable
and fast; a headless browser is not required for the core data.

## 2. Scope

### In scope (this build)
- On-demand scraping with short-TTL caching (a request triggers a live scrape;
  repeat requests within the TTL are served from cache).
- REST API service (read-only) covering:
  - Address/wallet profiles + their transaction, internal-tx, token-transfer, and
    NFT-transfer lists.
  - Token info, transfers, and holders.
  - Transaction details.
- Top-standard, fully Swagger-documented API.
- Security baseline (input validation / SSRF prevention, resource limits, leak-free
  errors, CORS + security headers). No inbound rate-limiting — the trusted main
  project is the only caller and owns that concern.
- Comprehensive tests (parser fixtures, mocked fetcher, service, API, opt-in live).

### Out of scope (deferred, by explicit decision)
- **Playwright browser fallback** — built later, after Approach A is built and tested.
  Architecture reserves a clean seam for it (the `Fetcher` interface).
- **Continuous monitoring / background crawler / datastore** — added later as a
  separate subsystem once the on-demand service is solid.
- Use of the official Etherscan/BaseScan JSON API.

## 3. Approach Decision

**Chosen: Approach A — HTTP + HTML parsing.**

Fetch pages with an async HTTP client (`httpx`) and parse server-rendered HTML
(`selectolax`). No browser per request.

| Approach | Verdict |
|----------|---------|
| **A. HTTP + parse** | **Chosen.** Fast, light, concurrent, simple deploy. Viable because tables are server-rendered. |
| B. Playwright per request | Rejected for now — slow/heavy, overkill when data is already in the HTML. Becomes the *fallback* later. |
| C. Hybrid (A primary, B fallback) | Deferred — this is the end-state after the Playwright fallback is added. |

Approach A is built behind a `Fetcher` interface so the Playwright fallback (→ Approach C)
drops in later without touching parsers, services, or the API.

## 4. Architecture

Layered design; each layer has one responsibility and communicates through a
well-defined interface.

```
   Bigger project
        |  HTTP (JSON)
+-------v-----------------------------------------+
|  API layer (FastAPI routers, /v1)               |  validation, JSON responses, Swagger
+-------------------------------------------------+
|  Service layer                                  |  orchestrates: cache? -> fetch -> parse -> cache
+--------------+----------------+-----------------+
|  Cache       |  Fetcher       |  Parsers        |
|  (TTL store) |  (interface)   |  (HTML->models) |
|              |   HttpFetcher  |                 |
|              |   [Playwright  |                 |
|              |    later]      |                 |
+--------------+----------------+-----------------+
        |
   basescan.org
```

### Components

| Component | Responsibility | Depends on |
|-----------|----------------|------------|
| **`Fetcher` (interface)** | URL/path -> raw HTML. Owns rate-limiting, retries, timeouts, headers, response-size cap. `HttpFetcher` implements it now. | httpx |
| **Parsers** | Pure functions: HTML string -> typed Pydantic model. One per page type. No network, no I/O. | selectolax, models |
| **Models** | Pydantic v2 schemas (the stable contract): `AddressProfile`, `TokenInfo`, `Transaction`, `TokenTransfer`, `NftTransfer`, `Holder`, pagination + error envelopes. | pydantic |
| **Cache** | Short-TTL store keyed by entity+page. In-memory (`cachetools`) now; Redis-swappable later behind a small interface. | cachetools |
| **Service layer** | Glue: check cache -> Fetcher -> Parser -> cache -> return model. Single definition of "how we get an entity." | fetcher, parsers, cache |
| **API layer** | FastAPI routers, request validation, error->HTTP mapping, OpenAPI metadata. Thin. | service, models |

**Invariant:** parsers never touch the network; fetchers never parse. This separation
makes the fetcher swappable and keeps parsers unit-testable against saved HTML.

### Suggested module layout
This is a **deployable API service, not a package** — there is no
`pyproject.toml`/`setup.py` and no `pip install -e .`. Dependencies live in
`requirements.txt`; the service runs via `uvicorn basescan_scraper.app:app`. Tests
import the code through `pytest.ini`'s `pythonpath = .`. Flat layout (no `src/`).
```
basescan_scraper/
  api/            # FastAPI app, routers, error handlers, OpenAPI config
  services/       # orchestration per entity
  fetchers/       # Fetcher interface + HttpFetcher
  parsers/        # one module per page type
  models/         # Pydantic schemas (response contracts)
  cache/          # cache interface + in-memory impl
  config.py       # env-based settings
tests/
  fixtures/       # saved BaseScan HTML
  unit/ ...       # parser, fetcher, service, api tests
  live/           # opt-in drift tests
requirements.txt      # runtime dependencies
requirements-dev.txt  # dev/test dependencies
pytest.ini            # test config (pythonpath, markers)
ruff.toml             # lint config
```

## 5. API Design

### Conventions
- **Versioned** under `/v1`. Resource-oriented, plural nouns, lowercase paths.
- `GET`-only (read-only service). Correct status codes; `Retry-After` on 503.
- JSON field names `snake_case`. Addresses normalized lowercase. Timestamps ISO 8601 UTC.
- **Monetary/quantity values returned as strings in raw wei** plus a human-readable
  decimal field — never JSON floats (avoids precision loss on large integers).

### Endpoints

| Method & path | Returns |
|---------------|---------|
| `GET /v1/addresses/{address}` | Address profile: ETH balance, USD value, token-holdings count & total value, funded-by, first/last tx |
| `GET /v1/addresses/{address}/transactions` | Normal transactions (paginated) |
| `GET /v1/addresses/{address}/internal-transactions` | Internal transactions (paginated) |
| `GET /v1/addresses/{address}/token-transfers` | ERC-20 transfers (paginated) |
| `GET /v1/addresses/{address}/nft-transfers` | NFT transfers (paginated) |
| `GET /v1/tokens/{address}` | Token info: price, supply, holders count |
| `GET /v1/tokens/{address}/transfers` | Token transfer list (paginated) |
| `GET /v1/tokens/{address}/holders` | Holder distribution (paginated) |
| `GET /v1/transactions/{hash}` | Transaction detail: from/to, value, gas, status, logs, transfers |
| `GET /health` | Liveness only — no scraping |

### Response shapes
List endpoints return a consistent paginated envelope:
```json
{
  "data": [ /* items */ ],
  "pagination": { "page": 1, "offset": 25, "total": 96, "has_next": true }
}
```
Single-resource endpoints return the resource object directly. Pagination mirrors
BaseScan's `page`/`offset`, with a **max page size cap** to prevent forced large scrapes.

### Errors — RFC 9457 Problem Details
Every error uses the same media-type shape, surfaced in Swagger:
```json
{ "type": "/errors/not-found", "title": "Address not found",
  "status": 404, "detail": "No data for 0x... on Base." }
```

### Swagger / OpenAPI quality
- Every route declares an explicit `response_model` -> exact schema in Swagger.
- OpenAPI `tags` group endpoints (Addresses, Tokens, Transactions).
- Every route has `summary` + `description`; every model field has `description` +
  realistic `examples` -> populated "Example Value" and "Schema" tabs.
- Documented response codes per endpoint (200/404/422/502/503/504) with example bodies.
- Stable `operation_id`s for clean client generation.
- Self-documenting `/docs` (Swagger UI) and `/redoc`; exportable OpenAPI spec.

## 6. Error Handling

| Condition | HTTP | Notes |
|-----------|------|-------|
| Invalid identifier (regex fail) | 422 | Rejected before any outbound request |
| Not found (tx hash that doesn't exist) | 404 | Tx-detail endpoint only (Plan 2). **Addresses never 404** — every valid address exists on-chain; an unused one legitimately returns zeros with HTTP 200. |
| BaseScan rate-limited / blocked us | 503 | Includes `Retry-After` |
| HTML changed -> parse failed (`ParseError`) | 502 | A required structural element (e.g. the address page's "ETH Balance" label) is missing, so we fail loudly rather than return silently-wrong zeros. |
| Upstream timeout | 504 | |

- `Fetcher` retries transient network errors with **exponential backoff** (base 0.5s,
  doubling, capped at 8s) plus a hard timeout and a response-size cap on every call.
- Internal exceptions and stack traces never appear in response bodies; upstream error
  handlers return only static, safe detail strings.
- The cached httpx client is closed on app shutdown via a FastAPI `lifespan`.

## 7. Security

Primary risks for a scraper that turns caller input into outbound URLs:
input-injection/SSRF, resource exhaustion, and internal-detail leakage.

- **Strict input validation** on every parameter before use:
  - address: `^0x[0-9a-fA-F]{40}$`
  - tx hash: `^0x[0-9a-fA-F]{64}$`
  - block / page / offset: bounded integers.
  - Non-matching input -> 422 before any URL is constructed.
- **SSRF prevention:** outbound URLs are always `fixed_base + validated_id`; caller
  input is never concatenated raw into a URL or used to choose a host.
- **Resource limits:** outbound timeouts, response-size caps, max page size, bounded
  concurrency.
- **No inbound rate-limiting** — only the trusted main project calls this service, so
  it owns that concern. Outbound requests still stay polite to BaseScan via the
  fetcher's throttle.
- Parsers only read HTML — never `eval`/execute scraped content.
- No secrets in code — all config via env vars; `.env` git-ignored.
- Restrictive CORS (internal service, not a public browser API).
- Logs scrub identifiers/values; no sensitive data logged.
- Pinned dependencies for supply-chain hygiene.

## 8. Testing Strategy

- **Parser unit tests** against saved HTML fixtures in `tests/fixtures/` — fast,
  offline, deterministic. The core of correctness.
- **Fetcher tests** with mocked HTTP: retries, timeouts, rate-limit handling, size caps.
- **Service tests** with a fake fetcher + fake cache: cache hit/miss, error propagation.
- **API tests** via FastAPI `TestClient`: validation, status codes, response shapes,
  error envelope.
- **Opt-in live tests** (pytest-marked, excluded from default run) that hit real
  BaseScan to detect HTML drift before it reaches production.

## 9. Open Questions / Future Work

- Playwright fallback (`PlaywrightFetcher`) — next phase after A is tested.
- Continuous monitoring subsystem (background watcher + datastore + change events).
- Optional Redis cache swap when scaling beyond a single instance.
- Deployment/runtime (container, host) — to be decided with the bigger project.
