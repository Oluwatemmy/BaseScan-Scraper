# Plan 3 — Contract Endpoint (source + ABI + metadata + proxy) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

> **COMMITS:** User commits manually via GitHub Desktop. **Do NOT run git** (commit/add/push). Pause at task ends for the user to commit.
> **VENV:** Use the venv interpreter for ALL commands: `.venv/Scripts/python.exe -m pytest …`, `.venv/Scripts/python.exe -m ruff check basescan_scraper tests`. Never bare `python`/`pytest`.

**Goal:** Add `GET /v1/contracts/{address}` returning a verified contract's source code, ABI, compiler metadata, constructor args, and proxy implementation address, parsed from the server-rendered `/address/{address}` page.

**Architecture:** Extends Plan 1/2a/2b/2c. New `models/contract.py`, `parsers/contract.py`, `ContractService`, and a `contracts` router. One httpx GET, no browser. Reuses validators, cache, error handlers, and the `NotFound`→404 mapping.

**Tech Stack:** Python 3.11+, FastAPI, httpx, selectolax, Pydantic v2, pytest, ruff (all present).

**Reference spec:** `docs/superpowers/specs/2026-06-30-plan3-contract-endpoint-design.md`

**Fixtures already captured** in `tests/fixtures/` (real BaseScan; do NOT re-download in tests):
- `contract_weth.html` — verified single-file contract (WETH, `0x4200000000000000000000000000000000000006`), not a proxy
- `contract_proxy_usdc.html` — verified 28-file proxy (USDC, `0x833589fcd6edb6e08f4c7c32d4f71b54bda02913`)
- `contract_unverified.html` — a contract with no verified source (`0xec0e36a6060339694c618ffffcc9ec7da21cb0cc`)
- `contract_eoa.html` — an EOA (`0x71c7656ec7ab88b098defb751b7401b5f6d8976f`)

**Verified ground truth (assert exactly):**
- WETH: `is_contract` true, `is_verified` true, `contract_name` "WETH9", 1 source file with `filename` "WETH9", `compiler_version` "v0.5.17+commit.d19bba13", `optimization_enabled` true, `optimization_runs` 10000, `evm_version` "default", `is_proxy` false, `implementation_address` null, `constructor_arguments` null, ABI present & JSON-parses to a list.
- USDC: `is_verified` true, `contract_name` "FiatTokenProxy", **28** source files (one filename contains `@openzeppelin/contracts/utils/Address.sol`), `is_proxy` true, `implementation_address` "0x2ce6311ddae708829bc0784c967b7d77d19fd779", `evm_version` "istanbul", `constructor_arguments` not null (hex), ABI present.
- Unverified: `is_contract` true, `is_verified` false, `source_files` [], `abi` null, `contract_name` null.
- EOA: `is_contract` false.

**Structural markers (verified):**
- Source files: `tree.css("input[name='chkContractFile']")`; each has `data-cname` (filename) and `data-csource` (full source). 0 inputs ⇒ unverified/EOA.
- ABI: `tree.css_first("pre#js-copytextarea2")` → JSON array text.
- is_contract: `tree.css_first("#ContentPlaceHolder1_li_contracts") is not None` (the contract tab; EOA lacks it).
- Metadata: an `<h6>` label box followed by the value element — e.g.
  `Contract Name </h6> <h4 ...> WETH9 </h4>`, `Compiler Version </h6> <div ...><span ...> v0.5.17+commit.d19bba13 </span></div>`,
  `Optimization Enabled </h6> <span ...> Yes <span>with</span> 10000 <span>runs</span> </span>`,
  `Other Settings </h6> <span ...> default <span>evmVersion</span> </span>` (EVM version = first token).
- Proxy: "Read as Proxy" present; implementation address near the literal `ImplementationAddress` → the `/address/0x…` link after it.
- Constructor Arguments: a `<pre>` whose text is a long hex string, in the "Constructor Arguments" section (USDC) — absent for WETH.

---

## File Structure
```
basescan_scraper/
  models/contract.py             # CREATE: SourceFile, ContractInfo
  parsers/contract.py            # CREATE: parse_contract + helpers
  services/contract_service.py   # CREATE: ContractService.get_contract
  api/deps.py                    # MODIFY: add get_contract_service
  api/routers/contracts.py       # CREATE: GET /v1/contracts/{address}
  app.py                         # MODIFY: include contracts router + openapi tag
tests/
  unit/test_models_contract.py        # CREATE
  unit/test_parser_contract_source.py # CREATE (source + abi + verified + is_contract)
  unit/test_parser_contract_meta.py   # CREATE (metadata + proxy + constructor args)
  unit/test_contract_service.py       # CREATE
  api/test_contracts_api.py           # CREATE
  live/test_live_drift.py             # MODIFY
```

---

## Task 1: Contract models

**Files:** Create `basescan_scraper/models/contract.py`; Test `tests/unit/test_models_contract.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/unit/test_models_contract.py
from basescan_scraper.models.contract import ContractInfo, SourceFile


def test_source_file():
    f = SourceFile(filename="WETH9", content="pragma solidity;")
    assert f.filename == "WETH9"


def test_contract_info_minimal():
    c = ContractInfo(address="0x" + "1" * 40, is_contract=False, is_verified=False)
    assert c.is_contract is False
    assert c.source_files == []
    assert c.abi is None
    assert c.is_proxy is False
```

- [ ] **Step 2: Run, expect FAIL** — `.venv/Scripts/python.exe -m pytest tests/unit/test_models_contract.py -v`

- [ ] **Step 3: Create `basescan_scraper/models/contract.py`**
```python
from typing import Optional

from pydantic import BaseModel, Field


class SourceFile(BaseModel):
    filename: str = Field(examples=["WETH9"])
    content: str


class ContractInfo(BaseModel):
    address: str
    is_contract: bool
    is_verified: bool
    contract_name: Optional[str] = None
    compiler_version: Optional[str] = Field(default=None, examples=["v0.5.17+commit.d19bba13"])
    optimization_enabled: Optional[bool] = None
    optimization_runs: Optional[int] = Field(default=None, examples=[10000])
    evm_version: Optional[str] = Field(default=None, examples=["default"])
    license_type: Optional[str] = Field(default=None, examples=["MIT"])
    source_files: list[SourceFile] = Field(default_factory=list)
    abi: Optional[list] = None
    constructor_arguments: Optional[str] = None
    is_proxy: bool = False
    implementation_address: Optional[str] = None
```

- [ ] **Step 4: Run, expect PASS**; full suite + ruff clean.
- [ ] **Step 5: Checkpoint** — user commits (`feat: contract models`).

---

## Task 2: parse_contract — source, ABI, verified, is_contract

**Files:** Create `basescan_scraper/parsers/contract.py`; Test `tests/unit/test_parser_contract_source.py`

- [ ] **Step 1: Write the failing tests**
```python
# tests/unit/test_parser_contract_source.py
import json
from pathlib import Path

from basescan_scraper.parsers.contract import is_contract_page, parse_contract

FX = Path(__file__).parent.parent / "fixtures"
WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"


def _html(name):
    return (FX / name).read_text(encoding="utf-8")


def test_is_contract_page():
    assert is_contract_page(_html("contract_weth.html")) is True
    assert is_contract_page(_html("contract_unverified.html")) is True
    assert is_contract_page(_html("contract_eoa.html")) is False


def test_weth_source_and_abi():
    c = parse_contract(_html("contract_weth.html"), address=WETH)
    assert c.address == WETH
    assert c.is_contract is True
    assert c.is_verified is True
    assert len(c.source_files) == 1
    assert c.source_files[0].filename == "WETH9"
    assert "pragma solidity" in c.source_files[0].content
    assert isinstance(c.abi, list) and len(c.abi) > 0  # parsed JSON


def test_usdc_multifile():
    c = parse_contract(_html("contract_proxy_usdc.html"), address=USDC)
    assert c.is_verified is True
    assert len(c.source_files) == 28
    assert any("@openzeppelin/contracts/utils/Address.sol" in f.filename for f in c.source_files)


def test_unverified_contract():
    c = parse_contract(_html("contract_unverified.html"),
                       address="0xec0e36a6060339694c618ffffcc9ec7da21cb0cc")
    assert c.is_contract is True
    assert c.is_verified is False
    assert c.source_files == []
    assert c.abi is None
    assert c.contract_name is None
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Create `basescan_scraper/parsers/contract.py`** (source/ABI/verified part):
```python
import json

from selectolax.parser import HTMLParser

from basescan_scraper.models.contract import ContractInfo, SourceFile
from basescan_scraper.parsers.common import ParseError, clean_text


def is_contract_page(html: str) -> bool:
    """True when the address is a contract (has the contract tab), not an EOA."""
    return HTMLParser(html).css_first("#ContentPlaceHolder1_li_contracts") is not None


def _source_files(tree: HTMLParser) -> list[SourceFile]:
    files: list[SourceFile] = []
    for inp in tree.css("input[name='chkContractFile']"):
        name = inp.attributes.get("data-cname")
        src = inp.attributes.get("data-csource")
        if name is not None and src is not None:
            files.append(SourceFile(filename=name, content=src))
    return files


def _abi(tree: HTMLParser) -> list | None:
    node = tree.css_first("pre#js-copytextarea2")
    if node is None:
        return None
    text = node.text(deep=True).strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ParseError(f"malformed ABI JSON: {exc}") from exc
    return parsed if isinstance(parsed, list) else None


def parse_contract(html: str, address: str) -> ContractInfo:
    tree = HTMLParser(html)
    is_contract = tree.css_first("#ContentPlaceHolder1_li_contracts") is not None
    source_files = _source_files(tree)
    abi = _abi(tree)
    is_verified = bool(source_files) or abi is not None
    return ContractInfo(
        address=address.lower(),
        is_contract=is_contract,
        is_verified=is_verified,
        source_files=source_files,
        abi=abi,
    )
```

- [ ] **Step 4: Run** until all PASS. Confirm exact counts (WETH 1 file, USDC 28).
- [ ] **Step 5:** Full suite + ruff clean. **Checkpoint** — user commits (`feat: contract source/ABI parser`).

---

## Task 3: parse_contract — metadata, proxy, constructor args

**Files:** Modify `basescan_scraper/parsers/contract.py`; Test `tests/unit/test_parser_contract_meta.py`

- [ ] **Step 1: Write the failing tests**
```python
# tests/unit/test_parser_contract_meta.py
from pathlib import Path

from basescan_scraper.parsers.contract import parse_contract

FX = Path(__file__).parent.parent / "fixtures"
WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"


def _html(name):
    return (FX / name).read_text(encoding="utf-8")


def test_weth_metadata():
    c = parse_contract(_html("contract_weth.html"), address=WETH)
    assert c.contract_name == "WETH9"
    assert c.compiler_version == "v0.5.17+commit.d19bba13"
    assert c.optimization_enabled is True
    assert c.optimization_runs == 10000
    assert c.evm_version == "default"
    assert c.is_proxy is False
    assert c.implementation_address is None
    assert c.constructor_arguments is None


def test_usdc_proxy_and_constructor():
    c = parse_contract(_html("contract_proxy_usdc.html"), address=USDC)
    assert c.contract_name == "FiatTokenProxy"
    assert c.evm_version == "istanbul"
    assert c.is_proxy is True
    assert c.implementation_address == "0x2ce6311ddae708829bc0784c967b7d77d19fd779"
    assert c.constructor_arguments is not None
    assert c.constructor_arguments.startswith("0") or c.constructor_arguments.startswith("0x")
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Add metadata extraction to `basescan_scraper/parsers/contract.py`.** Add the helpers and wire them into `parse_contract`. Inspect the fixtures to finalize selectors so the EXACT ground-truth values match:
```python
import re


def _meta_value(tree: HTMLParser, label: str) -> str | None:
    """Find the <h6> whose text == label, return the next element sibling's text."""
    for h6 in tree.css("h6"):
        if clean_text(h6.text(deep=True)) == label:
            sib = h6.next
            while sib is not None and (sib.tag == "-text" or not clean_text(sib.text(deep=True))):
                sib = sib.next
            return clean_text(sib.text(deep=True)) if sib is not None else None
    return None


def _implementation_address(html: str) -> str | None:
    m = re.search(r"ImplementationAddress[\s\S]{0,300}?/address/(0x[0-9a-fA-F]{40})", html)
    return m.group(1).lower() if m else None


_CTOR_RE = re.compile(r"Constructor Arguments[\s\S]{0,400}?([0-9a-fA-F]{64,})")


def _constructor_args(html: str) -> str | None:
    """The 'Constructor Arguments' section shows the raw ABI-encoded hex (a
    multiple of 64 hex chars). Absent for contracts with no constructor args."""
    m = _CTOR_RE.search(html)
    return m.group(1) if m else None
```
> NOTE: Step 3 is a starting point. In Step 4 you MUST finalize three things against the
> fixtures so the assertions pass exactly:
> 1. **Metadata via `_meta_value`** — `contract_name` ("WETH9"/"FiatTokenProxy"),
>    `compiler_version` ("v0.5.17+commit.d19bba13"). For `Optimization Enabled` the value text
>    is "Yes with 10000 runs": set `optimization_enabled = text.startswith("Yes")` and
>    `optimization_runs = int(re.search(r"(\d[\d,]*)\s*runs", text).group(1).replace(",",""))`.
>    For `Other Settings` the text is "default evmVersion": `evm_version = text.split()[0]`.
>    `license_type` is best-effort (nullable) — extract if a "License" label/value exists, else None.
> 2. **`is_proxy`** = `"Read as Proxy" in html`; `implementation_address` via `_implementation_address`
>    (USDC → "0x2ce6311ddae708829bc0784c967b7d77d19fd779"; WETH → None).
> 3. **`constructor_arguments`** — locate the "Constructor Arguments" section's hex `<pre>`
>    (USDC has one; WETH does not → None). Distinguish it from the bytecode `<pre>`s by its
>    proximity to the "Constructor Arguments" label, NOT by hex shape alone. Verify USDC returns
>    a non-empty hex string and WETH returns None.
> Wire all of these into `parse_contract`'s returned `ContractInfo`.

- [ ] **Step 4: Run** `.venv/Scripts/python.exe -m pytest tests/unit/test_parser_contract_meta.py -v` and iterate until all assertions pass with the EXACT ground-truth values. Do NOT weaken assertions.
- [ ] **Step 5:** Full suite + ruff clean. **Checkpoint** — user commits (`feat: contract metadata/proxy parser`).

---

## Task 4: ContractService + DI

**Files:** Create `basescan_scraper/services/contract_service.py`; Modify `basescan_scraper/api/deps.py`; Test `tests/unit/test_contract_service.py`

- [ ] **Step 1: Write the failing tests**
```python
# tests/unit/test_contract_service.py
from pathlib import Path

import pytest

from basescan_scraper.services.contract_service import ContractService
from basescan_scraper.services.transaction_service import NotFound

FX = Path(__file__).parent.parent / "fixtures"
WETH = "0x4200000000000000000000000000000000000006"
EOA = "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"


class PathFakeFetcher:
    def __init__(self):
        self.get_paths = []

    async def get(self, path: str) -> str:
        self.get_paths.append(path)
        if path == f"/address/{EOA}":
            return (FX / "contract_eoa.html").read_text(encoding="utf-8")
        return (FX / "contract_weth.html").read_text(encoding="utf-8")

    async def post_json(self, path, body):
        raise AssertionError("post_json not expected")


class DictCache:
    def __init__(self):
        self.store = {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v):
        self.store[k] = v


async def test_get_contract_verified_and_cached():
    f = PathFakeFetcher()
    svc = ContractService(f, DictCache())
    c = await svc.get_contract(WETH)
    assert c.is_verified is True and c.contract_name == "WETH9"
    await svc.get_contract(WETH)
    assert f.get_paths.count(f"/address/{WETH}") == 1  # cached


async def test_eoa_raises_not_found():
    svc = ContractService(PathFakeFetcher(), DictCache())
    with pytest.raises(NotFound):
        await svc.get_contract(EOA)
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Create `basescan_scraper/services/contract_service.py`**
```python
from basescan_scraper.cache.base import Cache
from basescan_scraper.fetchers.base import Fetcher
from basescan_scraper.models.contract import ContractInfo
from basescan_scraper.parsers.contract import is_contract_page, parse_contract
from basescan_scraper.services.transaction_service import NotFound


class ContractService:
    def __init__(self, fetcher: Fetcher, cache: Cache):
        self._fetcher = fetcher
        self._cache = cache

    async def get_contract(self, address: str) -> ContractInfo:
        key = f"contract:{address}"
        cached = await self._cache.get(key)
        if cached is not None:
            return ContractInfo.model_validate(cached)
        html = await self._fetcher.get(f"/address/{address}")
        if not is_contract_page(html):
            raise NotFound(address)
        info = parse_contract(html, address=address)
        await self._cache.set(key, info.model_dump())
        return info
```

- [ ] **Step 4: Add to `basescan_scraper/api/deps.py`**
```python
from basescan_scraper.services.contract_service import ContractService


def get_contract_service() -> ContractService:
    return ContractService(_fetcher(), _cache())
```
(`_fetcher()` / `_cache()` already exist in deps.py.)

- [ ] **Step 5: Run** until PASS; full suite + ruff clean. **Checkpoint** — user commits (`feat: contract service`).

---

## Task 5: contracts router

**Files:** Create `basescan_scraper/api/routers/contracts.py`; Modify `basescan_scraper/app.py`; Test `tests/api/test_contracts_api.py`

- [ ] **Step 1: Write the failing tests**
```python
# tests/api/test_contracts_api.py
from fastapi.testclient import TestClient

from basescan_scraper.app import create_app
from basescan_scraper.api.deps import get_contract_service
from basescan_scraper.models.contract import ContractInfo, SourceFile
from basescan_scraper.services.transaction_service import NotFound

ADDR = "0x4200000000000000000000000000000000000006"


class StubService:
    async def get_contract(self, address):
        return ContractInfo(address=address, is_contract=True, is_verified=True,
                            contract_name="WETH9",
                            source_files=[SourceFile(filename="WETH9", content="pragma;")],
                            abi=[{"type": "function"}])


class UnverifiedService:
    async def get_contract(self, address):
        return ContractInfo(address=address, is_contract=True, is_verified=False)


class EoaService:
    async def get_contract(self, address):
        raise NotFound(address)


def _client(service):
    app = create_app()
    app.dependency_overrides[get_contract_service] = lambda: service
    return TestClient(app)


def test_get_contract_verified():
    r = _client(StubService()).get(f"/v1/contracts/{ADDR}")
    assert r.status_code == 200
    body = r.json()
    assert body["contract_name"] == "WETH9"
    assert body["source_files"][0]["filename"] == "WETH9"
    assert body["is_verified"] is True


def test_get_contract_unverified_200():
    r = _client(UnverifiedService()).get(f"/v1/contracts/{ADDR}")
    assert r.status_code == 200
    assert r.json()["is_verified"] is False


def test_invalid_address_422():
    r = _client(StubService()).get("/v1/contracts/not-an-address")
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


def test_eoa_404():
    r = _client(EoaService()).get(f"/v1/contracts/{ADDR}")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Read an existing router** (`basescan_scraper/api/routers/tokens.py`) to match conventions, then create `basescan_scraper/api/routers/contracts.py`:
```python
from fastapi import APIRouter, Depends, Path

from basescan_scraper.api.deps import get_contract_service
from basescan_scraper.api.validators import normalize_address
from basescan_scraper.models.contract import ContractInfo
from basescan_scraper.services.contract_service import ContractService

router = APIRouter(prefix="/v1/contracts", tags=["Contracts"])

_RESPONSES = {
    404: {"description": "Address is not a contract (EOA)"},
    422: {"description": "Invalid address"},
    502: {"description": "Upstream unavailable / parse failure"},
    503: {"description": "Upstream rate limited"},
    504: {"description": "Upstream timeout"},
}
_ADDR_PATH = Path(..., examples=["0x4200000000000000000000000000000000000006"])


@router.get("/{address}", response_model=ContractInfo, summary="Get contract source + ABI",
            operation_id="getContract", responses=_RESPONSES)
async def get_contract(address: str = _ADDR_PATH,
                       service: ContractService = Depends(get_contract_service)) -> ContractInfo:
    """Verified contract source code, ABI, compiler metadata, and proxy implementation.
    Returns is_verified=false for unverified contracts; 404 for an EOA."""
    return await service.get_contract(normalize_address(address))
```

- [ ] **Step 4: Register in `basescan_scraper/app.py`** — add `contracts` to the routers import line, `app.include_router(contracts.router)`, and add `{"name": "Contracts", "description": "Verified contract source, ABI, and metadata."}` to `openapi_tags`.

- [ ] **Step 5: Run** the API tests until PASS (422 + 404 are `application/problem+json`). Full suite + ruff clean. **Boot smoke:** `.venv/Scripts/python.exe -c "from basescan_scraper.app import create_app; print('/v1/contracts/{address}' in create_app().openapi()['paths'])"` → `True`.
- [ ] **Step 6: Checkpoint** — user commits (`feat: contract endpoint`).

---

## Task 6: Live drift + cross-check + reviews

**Files:** Modify `tests/live/test_live_drift.py`

- [ ] **Step 1: Append a live test**
```python
@pytest.mark.live
async def test_live_contract_verified_and_proxy():
    from basescan_scraper.cache.memory import MemoryCache
    from basescan_scraper.fetchers.http_fetcher import HttpFetcher
    from basescan_scraper.services.contract_service import ContractService

    weth = "0x4200000000000000000000000000000000000006"
    usdc = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
    fetcher = HttpFetcher(get_settings())
    svc = ContractService(fetcher, MemoryCache(maxsize=10, ttl=0))
    try:
        w = await svc.get_contract(weth)
        u = await svc.get_contract(usdc)
    finally:
        await fetcher.aclose()
    # WETH: verified single-file, not a proxy
    assert w.is_verified is True and w.contract_name == "WETH9"
    assert len(w.source_files) >= 1 and "pragma solidity" in w.source_files[0].content
    assert isinstance(w.abi, list) and len(w.abi) > 0
    assert w.is_proxy is False
    # USDC: verified multi-file proxy
    assert u.is_verified is True and u.is_proxy is True
    assert u.implementation_address and u.implementation_address.startswith("0x")
    assert len(u.source_files) > 1
```

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/ -q` (live excluded, count unchanged) and `.venv/Scripts/python.exe -m pytest -m live -v` (all live pass; retry once on transient DNS). ruff clean.
- [ ] **Step 3: Playwright cross-check** — run the app; compare the API JSON for WETH and USDC against the live `/address/{addr}` Contract tab: contract name, compiler version, optimization runs, EVM version, source file count, ABI presence, is_proxy + implementation address. Fix any mismatch (browser-rendered value is the source of truth — see the percentage lesson in project memory).
- [ ] **Step 4:** Run `/code-review high` and `/security-review` over the diff; address findings (confirm: address validated before fetch; EOA→404, unverified→200, invalid→422 problem+json; ABI JSON parsed safely; no SSRF; no unbounded memory beyond the existing response cap; no secrets/leaks). Re-run full suite + `-m live` + ruff.
- [ ] **Step 5: Checkpoint** — user commits (`test: live drift + review fixes for contract endpoint`).

---

## Definition of Done
- `GET /v1/contracts/{address}` returns source + ABI + metadata + proxy for verified contracts; `is_verified=false` for unverified; 404 for EOA; 422 for invalid address.
- Offline suite green; `-m live` green; ruff clean; Playwright cross-check clean; code + security review done.
