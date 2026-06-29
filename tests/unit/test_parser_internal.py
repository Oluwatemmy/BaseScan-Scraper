from pathlib import Path

from basescan_scraper.parsers.address import parse_internal_transactions

FX = Path(__file__).parent.parent / "fixtures"


def test_parse_internal_transactions():
    html = (FX / "internal_donate.html").read_text(encoding="utf-8")
    rows = parse_internal_transactions(html)
    assert len(rows) == 8
    r = rows[0]
    assert r.parent_hash.startswith("0xb422713b8a582a") and len(r.parent_hash) == 66
    assert r.block == 47793754
    assert r.from_address == "0x12eada5fb3d4e515cd095035ae006aeb36bf179e"   # nuryale.base.eth
    assert r.to_address == "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"     # donate
    assert r.timestamp == "2026-06-25T08:40:55Z"   # single-digit hour zero-padded
    assert r.value.decimal == "0.00000073"
