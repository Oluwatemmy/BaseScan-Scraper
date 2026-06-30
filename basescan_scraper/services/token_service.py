from decimal import Decimal, InvalidOperation

from basescan_scraper.cache.base import Cache
from basescan_scraper.fetchers.base import Fetcher
from basescan_scraper.models.common import Page, Pagination
from basescan_scraper.models.token import TokenHolder, TokenInfo
from basescan_scraper.parsers.pagination import parse_pagination
from basescan_scraper.parsers.token import (
    is_token_not_found,
    parse_token_holders,
    parse_token_info,
)
from basescan_scraper.services.transaction_service import NotFound

_PCT_QUANTUM = Decimal("0.0001")  # BaseScan displays the holder % to 4 decimals


def _to_decimal(value: str | None) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(value.replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _fill_percentages(holders: list[TokenHolder], total_supply: str | None) -> None:
    """BaseScan computes holder % client-side as quantity / total_supply * 100.
    Replicate it here (4 decimals) since the server HTML carries only a
    placeholder. Leaves percentage None when supply or quantity is unparseable."""
    supply = _to_decimal(total_supply)
    if supply is None or supply <= 0:
        return
    for holder in holders:
        qty = _to_decimal(holder.quantity)
        if qty is None:
            continue
        pct = (qty / supply * 100).quantize(_PCT_QUANTUM)
        holder.percentage = f"{pct}%"


class TokenService:
    def __init__(self, fetcher: Fetcher, cache: Cache):
        self._fetcher = fetcher
        self._cache = cache

    async def get_info(self, address: str) -> TokenInfo:
        key = f"tokeninfo:{address}"
        cached = await self._cache.get(key)
        if cached is not None:
            return TokenInfo.model_validate(cached)
        html = await self._fetcher.get(f"/token/{address}")
        if is_token_not_found(html):
            raise NotFound(address)
        info = parse_token_info(html, address=address)
        await self._cache.set(key, info.model_dump())
        return info

    async def get_holders(self, address: str, page: int = 1, page_size: int = 50) -> Page:
        key = f"tokenholders:{address}:{page}:{page_size}"
        cached = await self._cache.get(key)
        if cached is not None:
            data = [TokenHolder.model_validate(x) for x in cached["data"]]
            return Page(data=data, pagination=Pagination(**cached["pagination"]))
        # Validate the token exists first (cached) so a non-token / non-existent
        # contract returns 404 — consistent with get_info — instead of an empty
        # 200. The holders fragment for a non-token renders an empty table
        # ("There are no matching entries"), which would otherwise look like a
        # real token with zero holders. The fetched info also supplies the total
        # supply used to compute each holder's percentage.
        info = await self.get_info(address)
        html = await self._fetcher.get(
            f"/token/generic-tokenholders2?a={address}&p={page}&ps={page_size}")
        holders, total = parse_token_holders(html, contract=address)
        _fill_percentages(holders, info.max_total_supply)
        _, total_pages = parse_pagination(html)
        pagination = Pagination(page=page, offset=page_size, total=total,
                                has_next=page < total_pages)
        await self._cache.set(key, {"data": [h.model_dump() for h in holders],
                                    "pagination": pagination.model_dump()})
        return Page(data=holders, pagination=pagination)
