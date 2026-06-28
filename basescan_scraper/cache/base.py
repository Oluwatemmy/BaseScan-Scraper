# basescan_scraper/cache/base.py
from typing import Any, Protocol


class Cache(Protocol):
    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any) -> None: ...
