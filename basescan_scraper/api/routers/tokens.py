from fastapi import APIRouter, Depends, Path, Query

from basescan_scraper.api.deps import get_token_service
from basescan_scraper.api.validators import normalize_address, validate_page, validate_page_size
from basescan_scraper.models.common import Page
from basescan_scraper.models.token import TokenHolder, TokenInfo
from basescan_scraper.services.token_service import TokenService

router = APIRouter(prefix="/v1/tokens", tags=["Tokens"])

_RESPONSES = {
    404: {"description": "Token not found"},
    422: {"description": "Invalid parameter"},
    502: {"description": "Upstream unavailable / parse failure"},
    503: {"description": "Upstream rate limited"},
    504: {"description": "Upstream timeout"},
}
# NOTE: no ge/le on the Query — bounds are enforced by validate_page/validate_page_size
# so out-of-range values raise OUR ValidationError (rendered as problem+json), not
# FastAPI's default 422 shape. The description documents the limits for Swagger.
_ADDR_PATH = Path(..., examples=["0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"])
_PAGE_Q = Query(default=None, description="1-based page number (>= 1)")
_SIZE_Q = Query(default=None, description="Items per page (1..100, default 50)")


@router.get("/{contract}", response_model=TokenInfo, summary="Get token info",
            operation_id="getTokenInfo", responses=_RESPONSES)
async def get_token_info(contract: str = _ADDR_PATH,
                         service: TokenService = Depends(get_token_service)) -> TokenInfo:
    """ERC-20 token info: name, symbol, decimals, price, supply, holders count, market cap."""
    return await service.get_info(normalize_address(contract))


@router.get("/{contract}/holders", response_model=Page[TokenHolder],
            summary="List token holders (top 1,000)", operation_id="getTokenHolders",
            responses=_RESPONSES)
async def get_token_holders(contract: str = _ADDR_PATH, page: int = _PAGE_Q,
                            page_size: int = _SIZE_Q,
                            service: TokenService = Depends(get_token_service)) -> Page[TokenHolder]:
    """Token holders, paginated. BaseScan lists only the top 1,000 holders."""
    return await service.get_holders(normalize_address(contract),
                                     validate_page(page), validate_page_size(page_size))
