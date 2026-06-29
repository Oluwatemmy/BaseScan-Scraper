# basescan_scraper/services/address_service.py
from basescan_scraper.cache.base import Cache
from basescan_scraper.fetchers.base import Fetcher
from basescan_scraper.models.address import (
    AddressProfile,
    InternalTransaction,
    NftTransfer,
    TokenTransfer,
    Transaction,
)
from basescan_scraper.models.common import Page, Pagination
from basescan_scraper.parsers.address import (
    parse_address_profile,
    parse_internal_transactions,
    parse_token_transfers,
    parse_transactions,
)
from basescan_scraper.parsers.nft import parse_nft_transfers
from basescan_scraper.parsers.pagination import parse_pagination

_NFT_PATH = "/nft-transfers.aspx/GetTableData_NftTransfers"
_NFT_COLUMNS = [
    {"data": d, "name": "", "searchable": True, "orderable": False,
     "search": {"value": "", "regex": False}}
    for d in ["preview", "txhash", "txMethod", "txMethodCustom", "blockNumber",
              "dt", "_from", "arrow", "_to", "type", "tokenAddress"]
]


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

    async def _paginated_html(self, list_path: str, address: str, page: int,
                              page_size: int, row_parser, model) -> Page:
        key = f"{list_path}:{address}:{page}:{page_size}"
        cached = await self._cache.get(key)
        if cached is not None:
            data = [model.model_validate(x) for x in cached["data"]]
            return Page(data=data, pagination=Pagination(**cached["pagination"]))
        html = await self._fetcher.get(f"/{list_path}?a={address}&p={page}&ps={page_size}")
        rows = row_parser(html)
        total, total_pages = parse_pagination(html)
        pagination = Pagination(page=page, offset=page_size, total=total,
                                has_next=page < total_pages)
        await self._cache.set(key, {"data": [r.model_dump() for r in rows],
                                    "pagination": pagination.model_dump()})
        return Page(data=rows, pagination=pagination)

    async def get_transactions(self, address: str, page: int = 1, page_size: int = 50) -> Page:
        return await self._paginated_html("txs", address, page, page_size,
                                          parse_transactions, Transaction)

    async def get_internal_transactions(self, address: str, page: int = 1, page_size: int = 50) -> Page:
        return await self._paginated_html("txsInternal", address, page, page_size,
                                          parse_internal_transactions, InternalTransaction)

    async def get_token_transfers(self, address: str, page: int = 1, page_size: int = 50) -> Page:
        return await self._paginated_html("tokentxns", address, page, page_size,
                                          parse_token_transfers, TokenTransfer)

    async def get_nft_transfers(self, address: str, page: int = 1, page_size: int = 25) -> Page:
        key = f"nft:{address}:{page}:{page_size}"
        cached = await self._cache.get(key)
        if cached is not None:
            data = [NftTransfer.model_validate(x) for x in cached["data"]]
            return Page(data=data, pagination=Pagination(**cached["pagination"]))
        body = {"dataTableModel": {
            "draw": 1, "columns": _NFT_COLUMNS, "order": [],
            "start": (page - 1) * page_size, "length": page_size,
            "search": {"value": "", "regex": False}, "Ext": address}}
        text = await self._fetcher.post_json(_NFT_PATH, body)
        rows, total = parse_nft_transfers(text)
        has_next = total is not None and page * page_size < total
        pagination = Pagination(page=page, offset=page_size, total=total, has_next=has_next)
        await self._cache.set(key, {"data": [r.model_dump() for r in rows],
                                    "pagination": pagination.model_dump()})
        return Page(data=rows, pagination=pagination)
