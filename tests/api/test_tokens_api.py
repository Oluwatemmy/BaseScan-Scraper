from fastapi.testclient import TestClient

from basescan_scraper.app import create_app
from basescan_scraper.api.deps import get_token_service
from basescan_scraper.models.common import Page, Pagination
from basescan_scraper.models.token import TokenHolder, TokenInfo
from basescan_scraper.services.transaction_service import NotFound

USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"


class StubService:
    async def get_info(self, address):
        return TokenInfo(address=address, name="USDC", symbol="USDC", type="ERC-20", decimals=6)

    async def get_holders(self, address, page=1, page_size=50):
        return Page(data=[TokenHolder(rank=1, address="0x" + "2" * 40, quantity="1", percentage="0%")],
                    pagination=Pagination(page=1, offset=50, total=1000, has_next=True))


class NotFoundService:
    async def get_info(self, address):
        raise NotFound(address)

    async def get_holders(self, address, page=1, page_size=50):
        raise NotFound(address)


def _client(service):
    app = create_app()
    app.dependency_overrides[get_token_service] = lambda: service
    return TestClient(app)


def test_get_token_info():
    r = _client(StubService()).get(f"/v1/tokens/{USDC}")
    assert r.status_code == 200
    assert r.json()["symbol"] == "USDC"


def test_get_token_holders_envelope():
    r = _client(StubService()).get(f"/v1/tokens/{USDC}/holders")
    assert r.status_code == 200
    body = r.json()
    assert body["pagination"]["total"] == 1000
    assert body["data"][0]["rank"] == 1


def test_invalid_contract_422():
    r = _client(StubService()).get("/v1/tokens/not-an-address")
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


def test_page_size_over_cap_422():
    r = _client(StubService()).get(f"/v1/tokens/{USDC}/holders?page_size=101")
    assert r.status_code == 422


def test_not_found_404():
    r = _client(NotFoundService()).get(f"/v1/tokens/{USDC}")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


def test_holders_not_found_404():
    r = _client(NotFoundService()).get(f"/v1/tokens/{USDC}/holders")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
