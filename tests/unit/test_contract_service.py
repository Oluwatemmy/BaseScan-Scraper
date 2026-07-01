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
