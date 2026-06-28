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
