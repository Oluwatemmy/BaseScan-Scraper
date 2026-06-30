from fastapi.testclient import TestClient

from basescan_scraper.app import create_app
from basescan_scraper.api.deps import get_transaction_service
from basescan_scraper.models.common import Amount
from basescan_scraper.models.transaction import EventLog, InputData, TransactionDetail
from basescan_scraper.services.transaction_service import NotFound

HASH = "0x" + "b" * 64


class StubService:
    async def get_transaction(self, tx_hash):
        return TransactionDetail(
            hash=tx_hash, status="success", block=1, from_address="0x" + "1" * 40,
            value=Amount.from_wei("0", symbol="ETH"),
            transaction_fee=Amount.from_wei("0", symbol="ETH"),
            gas_price=Amount.from_wei("0", decimals=9, symbol="Gwei"),
            gas_limit=21000, gas_used=21000, input=InputData(raw_hex="0x"))

    async def get_logs(self, tx_hash):
        return [EventLog(contract_address="0x" + "3" * 40, topics=["0xabc"], data="0x")]


class NotFoundService:
    async def get_transaction(self, tx_hash):
        raise NotFound(tx_hash)

    async def get_logs(self, tx_hash):
        raise NotFound(tx_hash)


def _client(service):
    app = create_app()
    app.dependency_overrides[get_transaction_service] = lambda: service
    return TestClient(app)


def test_get_transaction():
    r = _client(StubService()).get(f"/v1/transactions/{HASH}")
    assert r.status_code == 200
    assert r.json()["hash"] == HASH


def test_get_logs_envelope():
    r = _client(StubService()).get(f"/v1/transactions/{HASH}/logs")
    assert r.status_code == 200
    assert r.json()["data"][0]["contract_address"].startswith("0x")


def test_invalid_hash_422():
    r = _client(StubService()).get("/v1/transactions/0xnothex")
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


def test_not_found_404():
    r = _client(NotFoundService()).get(f"/v1/transactions/{HASH}")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


class TooLargeService:
    async def get_transaction(self, tx_hash):
        from basescan_scraper.fetchers.base import ResponseTooLarge
        raise ResponseTooLarge("13672523 bytes")

    async def get_logs(self, tx_hash):
        from basescan_scraper.fetchers.base import ResponseTooLarge
        raise ResponseTooLarge("13672523 bytes")


def test_response_too_large_502():
    # a huge tx page (exceeds the size cap) must surface as a clean 502 problem+json,
    # never a 500. Regression for an unhandled ResponseTooLarge.
    r = _client(TooLargeService()).get(f"/v1/transactions/{HASH}")
    assert r.status_code == 502
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["type"] == "/errors/upstream-too-large"
