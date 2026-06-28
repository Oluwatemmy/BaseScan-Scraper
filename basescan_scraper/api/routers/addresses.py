# basescan_scraper/api/routers/addresses.py
from fastapi import APIRouter, Depends, Path

from basescan_scraper.api.deps import get_address_service
from basescan_scraper.api.validators import normalize_address
from basescan_scraper.models.address import AddressProfile, Transaction
from basescan_scraper.models.common import Page, Pagination
from basescan_scraper.services.address_service import AddressService

router = APIRouter(prefix="/v1/addresses", tags=["Addresses"])

_RESPONSES = {
    422: {"description": "Invalid parameter"},
    502: {"description": "Upstream unavailable / parse failure"},
    503: {"description": "Upstream rate limited"},
    504: {"description": "Upstream timeout"},
}


@router.get("/{address}", response_model=AddressProfile, summary="Get address profile",
            operation_id="getAddressProfile", responses=_RESPONSES)
async def get_profile(
    address: str = Path(..., examples=["0x71c7656ec7ab88b098defb751b7401b5f6d8976f"]),
    service: AddressService = Depends(get_address_service),
) -> AddressProfile:
    """ETH balance, USD value, and token-holdings summary for an address."""
    addr = normalize_address(address)
    return await service.get_profile(addr)


@router.get("/{address}/transactions", response_model=Page[Transaction],
            summary="List address transactions", operation_id="getAddressTransactions",
            responses=_RESPONSES)
async def get_transactions(
    address: str = Path(..., examples=["0x71c7656ec7ab88b098defb751b7401b5f6d8976f"]),
    service: AddressService = Depends(get_address_service),
) -> Page[Transaction]:
    """Most recent normal transactions for an address (server-rendered page 1)."""
    addr = normalize_address(address)
    txs = await service.get_transactions(addr)
    pagination = Pagination(page=1, offset=len(txs) or 1, total=len(txs), has_next=False)
    return Page[Transaction](data=txs, pagination=pagination)
