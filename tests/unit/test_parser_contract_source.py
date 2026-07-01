from pathlib import Path

from basescan_scraper.parsers.contract import is_contract_page, parse_contract

FX = Path(__file__).parent.parent / "fixtures"
WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"


def _html(name):
    return (FX / name).read_text(encoding="utf-8")


def test_is_contract_page():
    assert is_contract_page(_html("contract_weth.html")) is True
    assert is_contract_page(_html("contract_unverified.html")) is True
    assert is_contract_page(_html("contract_eoa.html")) is False


def test_weth_source_and_abi():
    c = parse_contract(_html("contract_weth.html"), address=WETH)
    assert c.address == WETH
    assert c.is_contract is True
    assert c.is_verified is True
    assert len(c.source_files) == 1
    assert c.source_files[0].filename == "WETH9"
    assert "pragma solidity" in c.source_files[0].content
    assert isinstance(c.abi, list) and len(c.abi) > 0


def test_usdc_multifile():
    c = parse_contract(_html("contract_proxy_usdc.html"), address=USDC)
    assert c.is_verified is True
    assert len(c.source_files) == 28
    assert any("@openzeppelin/contracts/utils/Address.sol" in f.filename for f in c.source_files)


def test_malformed_abi_degrades_to_null_not_502():
    # A non-JSON / drifted ABI blob must yield abi=None (graceful), NOT raise
    # ParseError -> 502. A valid ABI still parses to a list.
    from selectolax.parser import HTMLParser

    from basescan_scraper.parsers.contract import _abi
    assert _abi(HTMLParser("<pre id='js-copytextarea2'>not verified</pre>")) is None
    assert _abi(HTMLParser('<pre id="js-copytextarea2">[{"type":"event"}]</pre>')) == [
        {"type": "event"}
    ]


def test_unverified_contract():
    c = parse_contract(_html("contract_unverified.html"),
                       address="0xec0e36a6060339694c618ffffcc9ec7da21cb0cc")
    assert c.is_contract is True
    assert c.is_verified is False
    assert c.source_files == []
    assert c.abi is None
    assert c.contract_name is None
