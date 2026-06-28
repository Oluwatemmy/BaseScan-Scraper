# basescan_scraper/cache/memory.py
from typing import Any

from cachetools import TTLCache


class MemoryCache:
    """In-process TTL cache. ttl=0 disables caching entirely."""

    def __init__(self, maxsize: int, ttl: int):
        self._store: TTLCache | None = TTLCache(maxsize=maxsize, ttl=ttl) if ttl > 0 else None

    async def get(self, key: str) -> Any | None:
        if self._store is None:
            return None
        return self._store.get(key)

    async def set(self, key: str, value: Any) -> None:
        if self._store is None:
            return
        self._store[key] = value
