# BaseScan Scraper

A read-only REST API that scrapes [basescan.org](https://basescan.org) (the Base L2
block explorer) and serves clean JSON. Built to be consumed by a larger project over
HTTP. It is a **deployable service, not a package** — no API keys required.

- **Approach:** plain HTTP fetch (`httpx`) + server-rendered HTML parsing
  (`selectolax`) behind a swappable `Fetcher` interface. No headless browser.
- **On-demand** scraping with short-TTL caching.
- Self-documenting Swagger UI at `/docs` and ReDoc at `/redoc`.

## Setup

Requires Python 3.11+. Use a virtual environment (never install globally):

```bash
python -m venv .venv
# Windows (Git Bash): .venv/Scripts/python.exe   |  macOS/Linux: .venv/bin/python
.venv/Scripts/python.exe -m pip install -r requirements.txt        # runtime only
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt    # + tests/lint
```

Optional config via environment variables (see `.env.example` for all of them and
their defaults) — e.g. `CACHE_TTL_SECONDS`, `REQUEST_TIMEOUT_SECONDS`,
`ALLOWED_ORIGINS`.

## Run

```bash
.venv/Scripts/python.exe -m uvicorn basescan_scraper.app:app --port 8000
```

Then open http://127.0.0.1:8000/docs for the interactive API docs.

## Endpoints (v1)

| Method & path | Description |
|---------------|-------------|
| `GET /health` | Liveness check (no scraping) |
| `GET /v1/addresses/{address}` | Address profile: ETH balance, USD value, token-holdings count & value, funded-by |
| `GET /v1/addresses/{address}/transactions` | Recent transactions (paginated envelope) |

`{address}` must be `0x` + 40 hex chars; anything else returns `422`
`application/problem+json`. Monetary values are returned as exact **wei strings** plus
a human-readable decimal — never floats.

Example:

```bash
curl http://127.0.0.1:8000/v1/addresses/0x71c7656ec7ab88b098defb751b7401b5f6d8976f
```

## Tests

```bash
.venv/Scripts/python.exe -m pytest          # unit + API tests (offline, fast)
.venv/Scripts/python.exe -m pytest -m live  # opt-in: hits real basescan.org (drift check)
.venv/Scripts/python.exe -m ruff check basescan_scraper tests
```

Parser tests run against a saved HTML fixture in `tests/fixtures/` for deterministic,
offline verification. The opt-in `live` test detects when BaseScan's HTML drifts.

## Design & scope

- Design spec: [`docs/superpowers/specs/2026-06-28-basescan-scraper-design.md`](docs/superpowers/specs/2026-06-28-basescan-scraper-design.md)
- Implementation plan: [`docs/superpowers/plans/2026-06-28-basescan-scraper-foundation-address.md`](docs/superpowers/plans/2026-06-28-basescan-scraper-foundation-address.md)

**Deferred to follow-on work (Plan 2):** token endpoints, transaction-detail endpoint,
internal-transactions / token-transfer / NFT-transfer lists, real multi-page
pagination, a Playwright fallback fetcher (drops into the existing `Fetcher`
interface), and continuous monitoring.
