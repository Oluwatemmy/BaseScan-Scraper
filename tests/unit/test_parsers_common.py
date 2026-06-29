# tests/unit/test_parsers_common.py
from basescan_scraper.parsers.common import (
    clean_text,
    parse_wei_from_eth_text,
    to_iso_utc,
)


def test_clean_text_strips_inline_tags_and_whitespace():
    assert clean_text("  0.30906125826241616   ETH ") == "0.30906125826241616 ETH"


def test_parse_wei_from_eth_text():
    assert parse_wei_from_eth_text("0.30906125826241616 ETH") == "309061258262416160"


def test_parse_wei_handles_commas_and_symbol():
    # 1,234.5 ETH == 1234.5 * 10**18 wei (comma is a thousands separator).
    assert parse_wei_from_eth_text("1,234.5 ETH") == "1234500000000000000000"


def test_to_iso_utc_two_digit_hour():
    assert to_iso_utc("2026-06-25 23:07:45") == "2026-06-25T23:07:45Z"


def test_to_iso_utc_single_digit_hour_is_zero_padded():
    assert to_iso_utc("2026-06-25 8:40:55") == "2026-06-25T08:40:55Z"


def test_to_iso_utc_bad_input_returns_none():
    assert to_iso_utc("not a date") is None
    assert to_iso_utc("") is None
    assert to_iso_utc(None) is None
