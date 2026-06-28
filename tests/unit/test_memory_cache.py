# tests/unit/test_memory_cache.py
from basescan_scraper.cache.memory import MemoryCache


async def test_set_then_get_returns_value():
    c = MemoryCache(maxsize=10, ttl=60)
    await c.set("k", {"v": 1})
    assert await c.get("k") == {"v": 1}


async def test_missing_key_returns_none():
    c = MemoryCache(maxsize=10, ttl=60)
    assert await c.get("absent") is None


async def test_ttl_zero_disables_cache():
    c = MemoryCache(maxsize=10, ttl=0)
    await c.set("k", 1)
    assert await c.get("k") is None
