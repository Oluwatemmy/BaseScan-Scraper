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
