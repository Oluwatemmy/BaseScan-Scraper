# tests/api/test_addresses_api.py
import pytest
from fastapi.testclient import TestClient

from basescan_scraper.app import create_app
from basescan_scraper.api.deps import get_address_service
from basescan_scraper.models.address import AddressProfile, Transaction
from basescan_scraper.models.common import Amount

ADDR = "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"


class StubService:
    async def get_profile(self, address: str) -> AddressProfile:
        return AddressProfile(address=address, eth_balance=Amount.from_wei("123", symbol="ETH"),
                              token_holdings_count=2)

    async def get_transactions(self, address: str) -> list[Transaction]:
        return [Transaction(hash="0x" + "a" * 64, block=1, from_address=ADDR,
                            to_address=None, value=Amount.from_wei("0", symbol="ETH"))]


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_address_service] = lambda: StubService()
    return TestClient(app)


def test_get_address_profile(client):
    r = client.get(f"/v1/addresses/{ADDR}")
    assert r.status_code == 200
    body = r.json()
    assert body["address"] == ADDR
    assert body["eth_balance"]["wei"] == "123"


def test_get_address_transactions_envelope(client):
    r = client.get(f"/v1/addresses/{ADDR}/transactions")
    assert r.status_code == 200
    body = r.json()
    assert "data" in body and "pagination" in body
    assert body["data"][0]["hash"].startswith("0x")


def test_invalid_address_returns_422_problem(client):
    r = client.get("/v1/addresses/not-an-address")
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["status"] == 422
