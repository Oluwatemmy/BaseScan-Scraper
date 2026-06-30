# tests/live/test_live_drift.py
import pytest

from basescan_scraper.config import get_settings
from basescan_scraper.fetchers.http_fetcher import HttpFetcher
from basescan_scraper.parsers.address import parse_address_profile, parse_transactions

ADDR = "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"


@pytest.mark.live
async def test_live_address_still_parses():
    fetcher = HttpFetcher(get_settings())
    try:
        html = await fetcher.get(f"/address/{ADDR}")
    finally:
        await fetcher.aclose()
    profile = parse_address_profile(html, address=ADDR)
    assert int(profile.eth_balance.wei) >= 0
    txs = parse_transactions(html)
    assert len(txs) > 0  # detects HTML drift in the transactions table
    # spot-check the first row has the shape we expect
    assert txs[0].hash.startswith("0x") and len(txs[0].hash) == 66
    assert txs[0].from_address.startswith("0x")
    assert int(txs[0].value.wei) >= 0


@pytest.mark.live
async def test_live_lists_parse_against_real_basescan():
    from basescan_scraper.services.address_service import AddressService
    from basescan_scraper.cache.memory import MemoryCache
    from basescan_scraper.fetchers.http_fetcher import HttpFetcher
    busy = "0x7a63e8fc1d0a5e9be52f05817e8c49d9e2d6efae"
    fetcher = HttpFetcher(get_settings())
    svc = AddressService(fetcher, MemoryCache(maxsize=10, ttl=0))
    try:
        txs = await svc.get_transactions(busy, page=1, page_size=50)
        internal = await svc.get_internal_transactions(busy, page=1, page_size=50)
        tokens = await svc.get_token_transfers(busy, page=1, page_size=50)
        nft = await svc.get_nft_transfers(busy, page=1, page_size=25)
    finally:
        await fetcher.aclose()
    # transactions: real total + rows
    assert txs.pagination.total and txs.pagination.total > 0
    assert all(t.hash.startswith("0x") and len(t.hash) == 66 for t in txs.data)
    # internal: list parses (may be empty for some addresses, but this one has txns)
    assert all(i.parent_hash.startswith("0x") for i in internal.data)
    # tokens: amount + symbol present
    assert all(isinstance(t.amount, str) for t in tokens.data)
    # nft: JSON endpoint + ERC type
    assert nft.pagination.total and nft.pagination.total > 0
    assert all(n.token_type.startswith("ERC-") for n in nft.data)
    assert all(n.hash.startswith("0x") and len(n.hash) == 66 for n in nft.data)


@pytest.mark.live
async def test_live_transaction_detail_and_logs():
    from basescan_scraper.services.transaction_service import TransactionService
    from basescan_scraper.cache.memory import MemoryCache
    from basescan_scraper.fetchers.http_fetcher import HttpFetcher
    h = "0xb239798ab298435ae661f8693bdc9ba52c7f04bae796d7d99f1cb7d976e2140d"
    fetcher = HttpFetcher(get_settings())
    svc = TransactionService(fetcher, MemoryCache(maxsize=10, ttl=0))
    try:
        tx = await svc.get_transaction(h)
        logs = await svc.get_logs(h)
    finally:
        await fetcher.aclose()
    assert tx.hash == h
    assert tx.block == 47819759
    assert tx.status == "success"
    assert tx.value.decimal == "0.011209138199984949"
    assert isinstance(logs, list)


@pytest.mark.live
async def test_live_token_info_and_holders():
    from basescan_scraper.cache.memory import MemoryCache
    from basescan_scraper.fetchers.http_fetcher import HttpFetcher
    from basescan_scraper.services.token_service import TokenService

    usdc = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
    fetcher = HttpFetcher(get_settings())
    svc = TokenService(fetcher, MemoryCache(maxsize=10, ttl=0))
    try:
        info = await svc.get_info(usdc)
        holders = await svc.get_holders(usdc, page=1, page_size=50)
    finally:
        await fetcher.aclose()
    # info: stable identity fields (price/supply drift, so don't assert exact)
    assert info.symbol == "USDC"
    assert info.decimals == 6
    assert info.holders_count and info.holders_count > 0
    assert info.price_usd is not None
    # holders: real rows, valid addresses, top-1,000 cap total
    assert len(holders.data) > 0
    assert all(h.address.startswith("0x") and len(h.address) == 42 for h in holders.data)
    assert all(h.rank > 0 for h in holders.data)
    assert holders.pagination.total == 1000
    # percentage is computed from supply (not the server "0.0000%" placeholder);
    # USDC's top holder holds several percent, so it must be a real non-zero %.
    top = holders.data[0]
    assert top.percentage and top.percentage.endswith("%")
    assert top.percentage != "0.0000%"
