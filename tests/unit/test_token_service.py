from pathlib import Path

import pytest

from basescan_scraper.models.common import Page
from basescan_scraper.services.token_service import TokenService
from basescan_scraper.services.transaction_service import NotFound

FX = Path(__file__).parent.parent / "fixtures"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"


class PathFakeFetcher:
    def __init__(self):
        self.get_paths = []

    async def get(self, path: str) -> str:
        self.get_paths.append(path)
        if path.startswith("/token/generic-tokenholders2"):
            return (FX / "token_holders_usdc.html").read_text(encoding="utf-8")
        if path == f"/token/{USDC}":
            return (FX / "token_usdc_info.html").read_text(encoding="utf-8")
        return (FX / "token_notfound.html").read_text(encoding="utf-8")

    async def post_json(self, path, body):
        raise AssertionError("post_json not expected")


class DictCache:
    def __init__(self):
        self.store = {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v):
        self.store[k] = v


async def test_get_info_and_cache():
    f = PathFakeFetcher()
    svc = TokenService(f, DictCache())
    info = await svc.get_info(USDC)
    assert info.symbol == "USDC" and info.decimals == 6
    await svc.get_info(USDC)
    assert f.get_paths.count(f"/token/{USDC}") == 1  # cached


async def test_get_holders_paginated():
    f = PathFakeFetcher()
    svc = TokenService(f, DictCache())
    page = await svc.get_holders(USDC, page=2, page_size=50)
    assert isinstance(page, Page)
    assert page.pagination.total == 1000
    assert len(page.data) == 50
    assert any("generic-tokenholders2?a=" in p and "p=2" in p and "ps=50" in p
               for p in f.get_paths)


async def test_info_not_found_raises():
    svc = TokenService(PathFakeFetcher(), DictCache())
    with pytest.raises(NotFound):
        await svc.get_info("0x" + "9" * 40)


async def test_holders_percentage_computed_from_supply():
    # BaseScan computes the holder % client-side; the service must replicate it
    # as quantity / total_supply * 100 (4 dp), NOT echo the "0.0000%" placeholder.
    svc = TokenService(PathFakeFetcher(), DictCache())
    page = await svc.get_holders(USDC, page=1, page_size=50)
    top = page.data[0]
    # 195,270,620.9949 / 4,207,496,819.876931 * 100 = 4.6410%
    assert top.percentage == "4.6410%"
    assert top.percentage != "0.0000%"


async def test_holders_not_found_raises():
    # A non-token contract must 404 on /holders too (consistent with get_info),
    # not return an empty 200. The fake serves token_notfound.html for the info
    # path of an unknown address.
    svc = TokenService(PathFakeFetcher(), DictCache())
    with pytest.raises(NotFound):
        await svc.get_holders("0x" + "9" * 40, page=1, page_size=50)
