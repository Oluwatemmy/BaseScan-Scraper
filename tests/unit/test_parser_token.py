from pathlib import Path

from basescan_scraper.parsers.address import parse_token_transfers

FX = Path(__file__).parent.parent / "fixtures"


def test_parse_token_transfers():
    html = (FX / "tokentxns_donate.html").read_text(encoding="utf-8")
    rows = parse_token_transfers(html)
    assert len(rows) == 50
    r = rows[0]
    assert r.hash.startswith("0xf15f81b9789103") and len(r.hash) == 66
    assert r.block == 47933577
    assert r.to_address == "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"
    assert r.amount == "382,277"
    assert r.token_address == "0x69681a2c965fe656cdc19dc970f65cc6ef7e0269"
    assert r.token_symbol == "Eos"
    assert r.token_name == "Eos"
    assert r.timestamp == "2026-06-28T14:21:41Z"


def test_parse_token_transfers_well_known_token_without_erc_prefix():
    # Well-known tokens (USDC) render as "USDC (USDC)" with NO "ERC-20:" prefix.
    # The token cell must still be found (via its /token/ link) and name/symbol parsed.
    html = (FX / "tokentxns_usdc.html").read_text(encoding="utf-8")
    rows = parse_token_transfers(html)
    usdc = next(r for r in rows if r.token_symbol == "USDC")
    assert usdc.token_name == "USDC"
    assert usdc.token_address == "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
    assert usdc.amount  # non-empty display amount
    # and a prefixed token in the same page still parses correctly
    squid = next((r for r in rows if r.token_symbol == "QUID"), None)
    if squid is not None:
        assert squid.token_name == "Squid"


def test_token_transfer_addresses_never_equal_contract():
    html = (FX / "tokentxns_donate.html").read_text(encoding="utf-8")
    for r in parse_token_transfers(html):
        if r.token_address:
            assert r.from_address != r.token_address
            assert r.to_address != r.token_address
