import pytest
from fastapi.testclient import TestClient

from basescan_scraper.app import create_app
from basescan_scraper.api.deps import get_address_service
from basescan_scraper.models.address import (
    InternalTransaction, NftTransfer, TokenTransfer, Transaction,
)
from basescan_scraper.models.common import Amount, Page, Pagination

ADDR = "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"


def _page(items):
    return Page(data=items, pagination=Pagination(page=1, offset=50, total=len(items), has_next=False))


class StubService:
    async def get_profile(self, address):
        from basescan_scraper.models.address import AddressProfile
        return AddressProfile(address=address, eth_balance=Amount.from_wei("1", symbol="ETH"))

    async def get_transactions(self, address, page=1, page_size=50):
        return _page([Transaction(hash="0x" + "a" * 64, block=1, from_address=ADDR,
                                  to_address=None, value=Amount.from_wei("0", symbol="ETH"))])

    async def get_internal_transactions(self, address, page=1, page_size=50):
        return _page([InternalTransaction(parent_hash="0x" + "b" * 64, block=1,
                      from_address=ADDR, to_address=None, value=Amount.from_wei("0", symbol="ETH"))])

    async def get_token_transfers(self, address, page=1, page_size=50):
        return _page([TokenTransfer(hash="0x" + "c" * 64, block=1, from_address=ADDR,
                      to_address=ADDR, amount="123", token_symbol="X")])

    async def get_nft_transfers(self, address, page=1, page_size=25):
        return _page([NftTransfer(hash="0x" + "d" * 64, block=1, from_address=ADDR,
                      to_address=ADDR, token_type="ERC-721")])


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_address_service] = lambda: StubService()
    return TestClient(app)


def test_get_address_profile(client):
    r = client.get(f"/v1/addresses/{ADDR}")
    assert r.status_code == 200
    assert r.json()["address"] == ADDR


@pytest.mark.parametrize("suffix", ["transactions", "internal-transactions",
                                    "token-transfers", "nft-transfers"])
def test_list_endpoints_envelope(client, suffix):
    r = client.get(f"/v1/addresses/{ADDR}/{suffix}")
    assert r.status_code == 200
    body = r.json()
    assert "data" in body and "pagination" in body
    item = body["data"][0]
    # InternalTransaction exposes the tx id as `parent_hash`; the rest use `hash`.
    assert item.get("hash", item.get("parent_hash", "")).startswith("0x")


def test_page_size_over_cap_422(client):
    r = client.get(f"/v1/addresses/{ADDR}/transactions?page_size=101")
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


def test_invalid_page_422(client):
    r = client.get(f"/v1/addresses/{ADDR}/transactions?page=0")
    assert r.status_code == 422


def test_invalid_address_422(client):
    r = client.get("/v1/addresses/not-an-address/transactions")
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")
