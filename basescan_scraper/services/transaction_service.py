from basescan_scraper.cache.base import Cache
from basescan_scraper.fetchers.base import Fetcher
from basescan_scraper.models.transaction import EventLog, TransactionDetail
from basescan_scraper.parsers.transaction import (
    is_tx_not_found,
    parse_event_logs,
    parse_transaction_detail,
)


class NotFound(Exception):
    """The requested transaction does not exist on BaseScan."""


class TransactionService:
    def __init__(self, fetcher: Fetcher, cache: Cache):
        self._fetcher = fetcher
        self._cache = cache

    async def _fetch_page(self, tx_hash: str) -> str:
        html = await self._fetcher.get(f"/tx/{tx_hash}")
        if is_tx_not_found(html):
            raise NotFound(tx_hash)
        return html

    async def get_transaction(self, tx_hash: str) -> TransactionDetail:
        key = f"txdetail:{tx_hash}"
        cached = await self._cache.get(key)
        if cached is not None:
            return TransactionDetail.model_validate(cached)
        tx = parse_transaction_detail(await self._fetch_page(tx_hash))
        await self._cache.set(key, tx.model_dump())
        return tx

    async def get_logs(self, tx_hash: str) -> list[EventLog]:
        key = f"txlogs:{tx_hash}"
        cached = await self._cache.get(key)
        if cached is not None:
            return [EventLog.model_validate(x) for x in cached]
        logs = parse_event_logs(await self._fetch_page(tx_hash))
        await self._cache.set(key, [x.model_dump() for x in logs])
        return logs
