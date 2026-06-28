# tests/unit/test_address_service.py
import pytest

from basescan_scraper.services.address_service import AddressService


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
    txs = await svc.get_transactions(addr)
    assert len(txs) > 0
    assert txs[0].hash.startswith("0x")
    # cached: second call doesn't refetch
    await svc.get_transactions(addr)
    assert fetcher.calls == 1
