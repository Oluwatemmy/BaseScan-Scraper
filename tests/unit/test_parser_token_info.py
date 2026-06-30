from pathlib import Path

import pytest

from basescan_scraper.parsers.common import ParseError
from basescan_scraper.parsers.token import is_token_not_found, parse_token_info

FX = Path(__file__).parent.parent / "fixtures"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"


def test_parse_token_info():
    html = (FX / "token_usdc_info.html").read_text(encoding="utf-8")
    t = parse_token_info(html, address=USDC)
    assert t.address == USDC
    assert t.name == "USDC"
    assert t.symbol == "USDC"
    assert t.type == "ERC-20"
    assert t.decimals == 6
    assert t.price_usd == "0.9996"
    assert t.market_cap_usd == "4,205,868,518.61"
    assert t.holders_count == 9858749
    assert t.max_total_supply == "4,207,496,819.876931"


def test_is_token_not_found():
    valid = (FX / "token_usdc_info.html").read_text(encoding="utf-8")
    missing = (FX / "token_notfound.html").read_text(encoding="utf-8")
    assert is_token_not_found(valid) is False
    assert is_token_not_found(missing) is True


def test_parse_token_info_raises_on_not_found():
    missing = (FX / "token_notfound.html").read_text(encoding="utf-8")
    with pytest.raises(ParseError):
        parse_token_info(missing, address="0x" + "1" * 40)
