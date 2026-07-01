from basescan_scraper.cache.base import Cache
from basescan_scraper.fetchers.base import Fetcher
from basescan_scraper.models.contract import ContractInfo
from basescan_scraper.parsers.contract import is_contract_page, parse_contract
from basescan_scraper.services.transaction_service import NotFound


class ContractService:
    def __init__(self, fetcher: Fetcher, cache: Cache):
        self._fetcher = fetcher
        self._cache = cache

    async def get_contract(self, address: str) -> ContractInfo:
        key = f"contract:{address}"
        cached = await self._cache.get(key)
        if cached is not None:
            return ContractInfo.model_validate(cached)
        html = await self._fetcher.get(f"/address/{address}")
        if not is_contract_page(html):
            raise NotFound(address)
        info = parse_contract(html, address=address)
        await self._cache.set(key, info.model_dump())
        return info
