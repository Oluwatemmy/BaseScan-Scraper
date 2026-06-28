# basescan_scraper/api/deps.py
from functools import lru_cache

from basescan_scraper.cache.memory import MemoryCache
from basescan_scraper.config import get_settings
from basescan_scraper.fetchers.http_fetcher import HttpFetcher
from basescan_scraper.services.address_service import AddressService


@lru_cache
def _fetcher() -> HttpFetcher:
    return HttpFetcher(get_settings())


@lru_cache
def _cache() -> MemoryCache:
    s = get_settings()
    return MemoryCache(maxsize=s.cache_max_items, ttl=s.cache_ttl_seconds)


def get_address_service() -> AddressService:
    return AddressService(_fetcher(), _cache())
