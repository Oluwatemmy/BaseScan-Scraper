# tests/unit/test_address_service.py
from pathlib import Path

import pytest

from basescan_scraper.models.common import Page
from basescan_scraper.services.address_service import AddressService

FX = Path(__file__).parent.parent / "fixtures"


class FakeFetcher:
    def __init__(self, html: str):
        self._html = html
        self.calls = 0

    async def get(self, path: str) -> str:
        self.calls += 1
        return self._html


class DictCache:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value):
        self.store[key] = value


@pytest.fixture
def fixture_html():
    from pathlib import Path
    return (Path(__file__).parent.parent / "fixtures" / "address_donate.html").read_text(
        encoding="utf-8"
    )


async def test_get_profile_parses(fixture_html):
    svc = AddressService(FakeFetcher(fixture_html), DictCache())
    profile = await svc.get_profile("0x71c7656ec7ab88b098defb751b7401b5f6d8976f")
    assert profile.address == "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"
    assert int(profile.eth_balance.wei) >= 0


async def test_profile_is_cached(fixture_html):
    fetcher = FakeFetcher(fixture_html)
    svc = AddressService(fetcher, DictCache())
    addr = "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"
    await svc.get_profile(addr)
    await svc.get_profile(addr)
    assert fetcher.calls == 1  # second call served from cache


async def test_get_transactions_parses_and_caches(fixture_html):
    fetcher = FakeFetcher(fixture_html)
    svc = AddressService(fetcher, DictCache())
    addr = "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"
    page = await svc.get_transactions(addr, page=1, page_size=50)
    assert isinstance(page, Page)
    assert len(page.data) > 0
    assert page.data[0].hash.startswith("0x")
    # cached: second identical call doesn't refetch (key: txs:{addr}:1:50)
    await svc.get_transactions(addr, page=1, page_size=50)
    assert fetcher.calls == 1


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


ADDR2 = "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"


async def test_transactions_paginated_envelope():
    svc = AddressService(PathFakeFetcher(), DictCache())
    page = await svc.get_transactions(ADDR2, page=1, page_size=50)
    assert isinstance(page, Page)
    assert page.pagination.total == 96
    assert page.pagination.has_next is True       # page 1 of 2
    assert len(page.data) == 50


async def test_internal_and_token_and_nft():
    f = PathFakeFetcher()
    svc = AddressService(f, DictCache())
    internal = await svc.get_internal_transactions(ADDR2, page=1, page_size=50)
    assert internal.pagination.total == 8 and len(internal.data) == 8
    token = await svc.get_token_transfers(ADDR2, page=1, page_size=50)
    assert token.pagination.total == 402 and len(token.data) == 50
    nft = await svc.get_nft_transfers(ADDR2, page=1, page_size=25)
    assert nft.pagination.total == 152 and len(nft.data) == 25
    path, body = f.post_calls[0]
    assert path == "/nft-transfers.aspx/GetTableData_NftTransfers"
    assert body["dataTableModel"]["start"] == 0
    assert body["dataTableModel"]["length"] == 25
    assert body["dataTableModel"]["Ext"] == ADDR2


async def test_paths_carry_page_and_size():
    f = PathFakeFetcher()
    svc = AddressService(f, DictCache())
    await svc.get_transactions(ADDR2, page=2, page_size=50)
    assert any("/txs?a=" in p and "p=2" in p and "ps=50" in p for p in f.get_paths)
