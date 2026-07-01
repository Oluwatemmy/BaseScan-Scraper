# Plan 3 — Contract Endpoint (source + ABI + metadata + proxy) — Design Spec

**Date:** 2026-06-30
**Status:** Approved (pending final spec review)
**Builds on:** Plan 1/2a/2b/2c (same layered architecture; reuses validators, cache,
error handlers, and the existing `is_contract` detection from `parse_address_profile`).

## 1. Purpose

Expose a verified contract's **source code, ABI, compiler metadata, and proxy
implementation** so the consuming project can decode, display, and interact with Base
contracts. Single server-rendered fetch (`/address/{address}`); no browser.

## 2. Scope

### In scope
- `GET /v1/contracts/{address}` → `ContractInfo` (verification status, name, compiler
  metadata, full source (all files), ABI, constructor args, proxy implementation address).

### Out of scope
- **Read/Write Contract live values** — JS/RPC-gated (the page loads them client-side); the
  consuming project can call an RPC node itself. (Function *definitions* are in the ABI.)
- **Raw bytecode** (creation/deployed) — large blobs, rarely needed (user decision).
- **Auto-resolving the proxy implementation's source/ABI** — we return the implementation
  *address*; the consumer re-queries `GET /v1/contracts/{implementation}` (user decision).

## 3. Key findings (verified against captured fixtures)

All on the server-rendered `/address/{address}` page:
- **Source code** lives in per-file checkbox inputs:
  `<input name='chkContractFile' data-cname='<filename>' data-csource='<full source>'>`.
  One input per file → clean multi-file support. Verified single-file (WETH) = 1 input;
  multi-file proxy (USDC) = 28 inputs (`FiatTokenProxy.sol`, `@openzeppelin/.../Address.sol`,
  …); EOA/unverified = 0 inputs. selectolax reads the (HTML-unescaped) attribute values.
- **ABI**: `<pre id="js-copytextarea2">` containing the JSON array. Present for verified
  contracts, absent for EOA/unverified.
- **Metadata labels** (server-rendered): Contract Name, Compiler Version, Optimization
  Enabled (+ runs), EVM Version / "Other Settings" (e.g. "default", "istanbul"), License Type.
- **Constructor Arguments**: present (hex) when the contract had them (USDC yes, WETH no).
- **Proxy**: "Read as Proxy" present + an Implementation address (USDC yes, WETH no).
- **EOA vs unverified contract**: both have 0 source files + no ABI; distinguished by
  `is_contract` (reuse the existing `parse_address_profile` contract-tab detection).

## 4. API

`{address}` validated by the existing `normalize_address` (`^0x[0-9a-fA-F]{40}\Z`) before the
URL is built (unchanged SSRF posture).

### `GET /v1/contracts/{address}` → `ContractInfo`
| Field | Type | Notes |
|-------|------|-------|
| `address` | str | lowercased |
| `is_contract` | bool | false ⇒ EOA |
| `is_verified` | bool | source published & verified |
| `contract_name` | str\|null | e.g. "WETH9" |
| `compiler_version` | str\|null | e.g. "v0.5.17+commit.d19bba13" |
| `optimization_enabled` | bool\|null | |
| `optimization_runs` | int\|null | |
| `evm_version` | str\|null | e.g. "default" / "istanbul" |
| `license_type` | str\|null | e.g. "GNU GPLv3" / "MIT" |
| `source_files` | list[`SourceFile`] | `{filename: str, content: str}`; [] when unverified |
| `abi` | list\|null | parsed ABI JSON (array of objects) |
| `constructor_arguments` | str\|null | encoded hex, when present |
| `is_proxy` | bool | |
| `implementation_address` | str\|null | for proxies; consumer re-queries this contract |

`SourceFile`: `filename` (str — the `data-cname`), `content` (str — the `data-csource`).

### Behavior / errors
- Invalid address → **422** problem+json.
- **EOA** (`is_contract` false) → **404** (NotFound).
- **Unverified contract** (`is_contract` true, no verified source) → **200** with
  `is_verified=false`, `source_files=[]`, `abi=null`, and metadata fields null (still returns
  `is_contract:true`, `is_proxy`, etc.).
- Structural drift (e.g. ABI present but unparseable) → `ParseError` → **502**.
- Upstream failures → 502/503/504 (existing handlers).

## 5. Models

New `models/contract.py`: `SourceFile`, `ContractInfo` (fields above). `abi` is
`Optional[list]` (parsed JSON array; null when absent/unverified). Source/ABI strings are
returned as-is (display strings, like the rest of the project).

## 6. Parsers

New `parsers/contract.py`:
- `parse_contract(html, address) -> ContractInfo`.
- Source: `tree.css("input[name='chkContractFile']")` → `SourceFile(filename=data-cname,
  content=data-csource)` per input.
- ABI: `tree.css_first("pre#js-copytextarea2")` → `json.loads` (guard → ParseError on
  malformed JSON when the element is present).
- `is_verified`: True when ≥1 source file (or ABI present).
- `is_contract`: reuse the existing contract-tab detection
  (`#ContentPlaceHolder1_li_contracts`) from `parse_address_profile`/`parsers/address.py`.
- Metadata (Contract Name, Compiler Version, Optimization Enabled, runs, EVM Version,
  License Type), constructor args, `is_proxy` ("Read as Proxy"), `implementation_address` —
  extracted by label/structure; exact selectors finalized against the fixtures.
- Helper `is_eoa(html)` (or reuse `is_contract`) drives the 404.

**Fixtures (captured):** `contract_weth.html` (verified single-file, not a proxy),
`contract_proxy_usdc.html` (verified 28-file multi-file proxy), `contract_eoa.html`.
The plan also captures a **clean unverified contract** (is_contract true, 0 source files) and
confirms a **clean EOA** for the 404 path.

**Ground-truth anchors (verified):**
- WETH (`0x4200000000000000000000000000000000000006`): is_contract true, is_verified true,
  contract_name "WETH9", 1 source file (data-cname "WETH9"), ABI present & JSON-parseable,
  is_proxy false, no constructor args, optimization "Yes".
- USDC (`0x833589fcd6edb6e08f4c7c32d4f71b54bda02913`): is_verified true, **28 source files**
  (incl. `@openzeppelin/contracts/utils/Address.sol`), ABI present, **is_proxy true**,
  constructor_arguments present (hex `0000…6d0c9a70d85e42ba8b76dc06620d4e988ec8d0c1…`),
  EVM "istanbul".
- EOA fixture: is_verified false, 0 source files, ABI absent.

## 7. Service / DI

`ContractService(fetcher, cache)`:
- `get_contract(address) -> ContractInfo` — fetch `/address/{address}`; if `is_contract`
  false → raise `NotFound`; else `parse_contract`. Cache `contract:{address}`.
New `get_contract_service` dependency + a `contracts` router included in the app.

## 8. Testing

- Parser unit tests vs fixtures with exact assertions (WETH single-file values; USDC
  multi-file count + proxy + constructor args; unverified → is_verified false, []/null;
  ABI JSON-parses).
- Service tests with fake fetcher/cache (EOA → NotFound; verified → ContractInfo; caching).
- API tests (TestClient): verified → 200 + shape; unverified → 200 is_verified=false;
  EOA → 404; invalid address → 422 (problem+json).
- Opt-in live drift (WETH + USDC: stable fields — name, is_proxy, ≥1 source file, ABI list).
- Playwright cross-check (source/ABI/metadata/proxy vs the live page). Code + security review.

## 9. Definition of done
- `GET /v1/contracts/{address}` returns source + ABI + metadata + proxy for verified
  contracts; `is_verified=false` for unverified; 404 for EOA; 422 for invalid.
- Offline suite green; live drift green; ruff clean; cross-check clean; reviews done.
