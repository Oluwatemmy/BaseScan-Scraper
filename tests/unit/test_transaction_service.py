from pathlib import Path

import pytest

from basescan_scraper.services.transaction_service import NotFound, TransactionService

FX = Path(__file__).parent.parent / "fixtures"


class FakeFetcher:
    def __init__(self, name):
        self._html = (FX / name).read_text(encoding="utf-8")
        self.calls = 0

    async def get(self, path: str) -> str:
        self.calls += 1
        return self._html

    async def post_json(self, path, body):
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
    assert f.calls == 1  # cached page, no refetch


async def test_get_logs():
    svc = TransactionService(FakeFetcher("tx_token.html"), DictCache())
    logs = await svc.get_logs("0x" + "c" * 64)
    assert len(logs) > 0


async def test_not_found_raises():
    svc = TransactionService(FakeFetcher("tx_notfound.html"), DictCache())
    with pytest.raises(NotFound):
        await svc.get_transaction("0x" + "9" * 64)
