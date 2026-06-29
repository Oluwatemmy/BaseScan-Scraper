# tests/unit/test_parser_address.py
from pathlib import Path

import pytest

from basescan_scraper.parsers.address import parse_address_profile, parse_transactions
from basescan_scraper.parsers.common import ParseError

FIXTURE = Path(__file__).parent.parent / "fixtures" / "address_donate.html"
ADDR = "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"


def test_parse_profile_extracts_balance_and_holdings():
    html = FIXTURE.read_text(encoding="utf-8")
    profile = parse_address_profile(html, address=ADDR)
    assert profile.address == ADDR
    assert profile.eth_balance.wei.isdigit()
    assert int(profile.eth_balance.wei) > 0
    assert profile.eth_balance.decimal.startswith("0.")
    assert profile.token_holdings_count is None or profile.token_holdings_count > 0


def test_parse_profile_extracts_usd_and_funded_by():
    html = FIXTURE.read_text(encoding="utf-8")
    profile = parse_address_profile(html, address=ADDR)
    assert profile.eth_value_usd == "485.67"
    assert profile.token_holdings_value_usd == "71123407.61"
    assert profile.funded_by == "0xaf02632dd397a5338e5737b3f77b68d6524d2980"


def test_parse_profile_raises_on_missing_balance():
    with pytest.raises(ParseError):
        parse_address_profile("<html><body>nothing</body></html>", address=ADDR)


def test_parse_profile_detects_contract():
    html = (FIXTURE.parent / "address_usdc_contract.html").read_text(encoding="utf-8")
    p = parse_address_profile(html, address="0x833589fcd6edb6e08f4c7c32d4f71b54bda02913")
    assert p.is_contract is True


def test_parse_profile_eoa_is_not_contract():
    html = FIXTURE.read_text(encoding="utf-8")  # address_donate.html (EOA)
    p = parse_address_profile(html, address=ADDR)
    assert p.is_contract is False


def test_parse_transactions_first_row_enriched():
    html = FIXTURE.read_text(encoding="utf-8")
    txs = parse_transactions(html)
    first = txs[0]
    assert first.method == "Transfer"
    assert first.timestamp == "2026-06-25T23:07:45Z"
    assert first.txn_fee is not None
    assert first.txn_fee.decimal == "0.00000014"
    assert first.txn_fee.wei == "140000000000"


def test_parse_transactions_returns_rows():
    html = FIXTURE.read_text(encoding="utf-8")
    txs = parse_transactions(html)
    assert len(txs) > 0

    first = txs[0]
    assert first.hash == (
        "0xb239798ab298435ae661f8693bdc9ba52c7f04bae796d7d99f1cb7d976e2140d"
    )
    assert first.block == 47819759
    assert first.from_address == "0x3ae6963e43f804e455b123c2015cfc88fdfe02b5"
    assert first.to_address == "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"
    assert first.direction == "in"
    assert first.value.decimal == "0.01120913"
    assert first.value.wei == "11209130000000000"

    # sanity: every parsed tx has a full-length hash, and from/to (when present)
    # are always valid 40-hex addresses — never empty/missing for a normal row
    for tx in txs:
        assert tx.hash.startswith("0x") and len(tx.hash) == 66
        assert tx.from_address.startswith("0x") and len(tx.from_address) == 42
        if tx.to_address is not None:
            assert tx.to_address.startswith("0x") and len(tx.to_address) == 42


def test_parse_transactions_ens_named_counterparty_row():
    # Row 2 has an ENS-named sender ("oxmax.base.eth") that carries an
    # /address/ href but NO data-highlight-target, while the recipient
    # ("BaseScan: Donate") is a nametag with data-highlight-target only.
    # Both must be captured, in the correct From/To order.
    html = FIXTURE.read_text(encoding="utf-8")
    txs = parse_transactions(html)
    row = txs[1]
    assert row.hash == (
        "0x77e66bed0c3cbb934612435c56d75597336bb04b4961ff5bb77d96463126a0dd"
    )
    assert row.from_address == "0x1046394abffeec81be8c48136745a4a46917ccbc"  # oxmax.base.eth
    assert row.to_address == "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"   # donate
    assert row.direction == "in"


def test_parse_transactions_on_txs_page_full_precision():
    html = (FIXTURE.parent / "txs_donate_p1.html").read_text(encoding="utf-8")
    txs = parse_transactions(html)
    assert len(txs) == 50  # /txs default page size
    first = txs[0]
    assert first.hash == "0xb239798ab298435ae661f8693bdc9ba52c7f04bae796d7d99f1cb7d976e2140d"
    assert first.block == 47819759
    assert first.from_address == "0x3ae6963e43f804e455b123c2015cfc88fdfe02b5"
    assert first.to_address == "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"
    assert first.direction == "in"
    assert first.method == "Transfer"
    assert first.timestamp == "2026-06-25T23:07:45Z"
    # /txs shows fuller precision than the /address page
    assert first.value.decimal == "0.011209138199984"
    assert first.value.wei == "11209138199984000"
    assert first.txn_fee is not None and first.txn_fee.decimal == "0.00000014"
