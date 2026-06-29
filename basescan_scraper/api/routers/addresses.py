from fastapi import APIRouter, Depends, Path, Query

from basescan_scraper.api.deps import get_address_service
from basescan_scraper.api.validators import normalize_address, validate_page, validate_page_size
from basescan_scraper.models.address import (
    AddressProfile, InternalTransaction, NftTransfer, TokenTransfer, Transaction,
)
from basescan_scraper.models.common import Page
from basescan_scraper.services.address_service import AddressService

router = APIRouter(prefix="/v1/addresses", tags=["Addresses"])

_RESPONSES = {
    422: {"description": "Invalid parameter"},
    502: {"description": "Upstream unavailable / parse failure"},
    503: {"description": "Upstream rate limited"},
    504: {"description": "Upstream timeout"},
}
# NOTE: no ge/le on the Query — bounds are enforced by validate_page/validate_page_size
# so out-of-range values raise OUR ValidationError (rendered as problem+json), not
# FastAPI's default 422 shape. The description documents the limits for Swagger.
_ADDR_PATH = Path(..., examples=["0x71c7656ec7ab88b098defb751b7401b5f6d8976f"])
_PAGE_Q = Query(default=None, description="1-based page number (>= 1)")
_SIZE_Q = Query(default=None, description="Items per page (1..100, default 50)")


@router.get("/{address}", response_model=AddressProfile, summary="Get address profile",
            operation_id="getAddressProfile", responses=_RESPONSES)
async def get_profile(address: str = _ADDR_PATH,
                      service: AddressService = Depends(get_address_service)) -> AddressProfile:
    """ETH balance, USD value, and token-holdings summary for an address."""
    return await service.get_profile(normalize_address(address))


@router.get("/{address}/transactions", response_model=Page[Transaction],
            summary="List address transactions", operation_id="getAddressTransactions",
            responses=_RESPONSES)
async def get_transactions(address: str = _ADDR_PATH, page: int = _PAGE_Q, page_size: int = _SIZE_Q,
                           service: AddressService = Depends(get_address_service)) -> Page[Transaction]:
    """Normal transactions for an address (paginated)."""
    return await service.get_transactions(normalize_address(address),
                                          validate_page(page), validate_page_size(page_size))


@router.get("/{address}/internal-transactions", response_model=Page[InternalTransaction],
            summary="List internal transactions", operation_id="getAddressInternalTransactions",
            responses=_RESPONSES)
async def get_internal(address: str = _ADDR_PATH, page: int = _PAGE_Q, page_size: int = _SIZE_Q,
                       service: AddressService = Depends(get_address_service)) -> Page[InternalTransaction]:
    """Contract-internal transactions involving an address (paginated)."""
    return await service.get_internal_transactions(normalize_address(address),
                                                   validate_page(page), validate_page_size(page_size))


@router.get("/{address}/token-transfers", response_model=Page[TokenTransfer],
            summary="List ERC-20 token transfers", operation_id="getAddressTokenTransfers",
            responses=_RESPONSES)
async def get_token_transfers(address: str = _ADDR_PATH, page: int = _PAGE_Q, page_size: int = _SIZE_Q,
                              service: AddressService = Depends(get_address_service)) -> Page[TokenTransfer]:
    """ERC-20 token transfers involving an address (paginated)."""
    return await service.get_token_transfers(normalize_address(address),
                                             validate_page(page), validate_page_size(page_size))


@router.get("/{address}/nft-transfers", response_model=Page[NftTransfer],
            summary="List NFT transfers", operation_id="getAddressNftTransfers",
            responses=_RESPONSES)
async def get_nft_transfers(address: str = _ADDR_PATH, page: int = _PAGE_Q, page_size: int = _SIZE_Q,
                            service: AddressService = Depends(get_address_service)) -> Page[NftTransfer]:
    """ERC-721/ERC-1155 NFT transfers involving an address (paginated)."""
    return await service.get_nft_transfers(normalize_address(address),
                                           validate_page(page), validate_page_size(page_size))
