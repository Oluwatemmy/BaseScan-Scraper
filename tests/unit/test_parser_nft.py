from pathlib import Path

from basescan_scraper.parsers.nft import parse_nft_transfers

FX = Path(__file__).parent.parent / "fixtures"


def test_parse_nft_transfers():
    text = (FX / "nft_active.json").read_text(encoding="utf-8")
    rows, total = parse_nft_transfers(text)
    assert total == 152
    assert len(rows) == 25
    r = rows[0]
    assert r.hash == "0xfcb399511d2ebdf577be4bcdd3dc437898e3d2c86ef05f1b15eeffd503d92dbf"
    assert r.block == 46332875
    assert r.from_address == "0x7a63e8fc1d0a5e9be52f05817e8c49d9e2d6efae"
    assert r.to_address == "0x1c117e6cc629c414377fdbb427db329fd0821f9a"
    assert r.token_type == "ERC-1155"
    assert r.token_id == "6277101738291256769055125632938578558371868663393442798971"
    assert r.token_address == "0x01df6fb6a28a89d6bfa53b2b3f20644abf417678"
    assert r.collection_name == "SuperPositions"
    assert r.quantity == "14526371714"
    assert r.method == "Exec Transaction"
    assert r.timestamp == "2026-05-22T13:04:57Z"


def test_parse_nft_transfers_malformed_raises():
    import pytest

    from basescan_scraper.parsers.common import ParseError
    with pytest.raises(ParseError):
        parse_nft_transfers("not json")
