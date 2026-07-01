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

    Returns is_verified=false for unverified contracts; 404 for an EOA.
    """
    return await service.get_contract(normalize_address(address))
