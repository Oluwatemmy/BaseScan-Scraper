# basescan_scraper/services/address_service.py
from basescan_scraper.cache.base import Cache
from basescan_scraper.fetchers.base import Fetcher
from basescan_scraper.models.address import AddressProfile, Transaction
from basescan_scraper.parsers.address import parse_address_profile, parse_transactions


class AddressService:
    def __init__(self, fetcher: Fetcher, cache: Cache):
        self._fetcher = fetcher
        self._cache = cache

    async def get_profile(self, address: str) -> AddressProfile:
        key = f"profile:{address}"
        cached = await self._cache.get(key)
        if cached is not None:
            return AddressProfile.model_validate(cached)
        html = await self._fetcher.get(f"/address/{address}")
        profile = parse_address_profile(html, address=address)
        await self._cache.set(key, profile.model_dump())
        return profile

    async def get_transactions(self, address: str) -> list[Transaction]:
        key = f"txs:{address}"
        cached = await self._cache.get(key)
        if cached is not None:
            return [Transaction.model_validate(t) for t in cached]
        html = await self._fetcher.get(f"/address/{address}")
        txs = parse_transactions(html)
        await self._cache.set(key, [t.model_dump() for t in txs])
        return txs
