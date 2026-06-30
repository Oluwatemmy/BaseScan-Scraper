from pathlib import Path

from basescan_scraper.parsers.token import _looks_like_address, parse_token_holders

FX = Path(__file__).parent.parent / "fixtures"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"


def _holders_html(rows: str) -> str:
    return (
        "<div>Top 1,000 holders<span> (From a total of 5 holders)</span></div>"
        "<table><thead><tr><th>Rank</th><th>Address</th><th>Label</th>"
        "<th>Quantity</th><th>Percentage</th><th>Value</th><th>Analytics</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )


def test_parse_token_holders():
    html = (FX / "token_holders_usdc.html").read_text(encoding="utf-8")
    holders, total = parse_token_holders(html, contract=USDC)
    assert total == 1000  # BaseScan lists only the top 1,000
    assert len(holders) == 50
    h = holders[0]
    assert h.rank == 1
    assert h.address == "0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb"
    assert h.label == "Morpho: Morpho"
    assert h.quantity == "195,270,620.9949"
    # percentage is NOT parsed here (server HTML is a JS placeholder); the
    # service computes it from total supply.
    assert h.percentage is None
    assert h.value_usd == "195,195,051.26"


def test_looks_like_address():
    # truncated / full address displays -> treated as address (label dropped)
    assert _looks_like_address("0x1234...5678") is True
    assert _looks_like_address("0x" + "a" * 40) is True
    # genuine nametags starting with 0x -> NOT an address (label kept)
    assert _looks_like_address("0xVault") is False
    assert _looks_like_address("Morpho: Morpho") is False


def test_real_label_starting_with_0x_is_kept():
    c = USDC
    row = (
        f'<tr><td>1</td><td><a href="/token/{c}?a=0x{"1" * 40}">0xVault</a></td>'
        "<td></td><td>10</td><td>5%</td><td>$9</td><td></td></tr>"
    )
    holders, _ = parse_token_holders(_holders_html(row), contract=c)
    assert holders[0].label == "0xVault"
    assert holders[0].address == "0x" + "1" * 40


def test_address_with_extra_query_param_before_a():
    c = USDC
    row = (
        f'<tr><td>2</td><td><a href="/token/{c}?sid=x&a=0x{"2" * 40}">'
        "Some Tag</a></td><td></td><td>10</td><td>5%</td><td>$9</td><td></td></tr>"
    )
    holders, _ = parse_token_holders(_holders_html(row), contract=c)
    assert holders[0].address == "0x" + "2" * 40


def test_row_without_holder_address_is_skipped():
    c = USDC
    row = (
        "<tr><td>3</td><td><a href=\"/address/0x" + "3" * 40 + '">Not a holder link'
        "</a></td><td></td><td>10</td><td>5%</td><td>$9</td><td></td></tr>"
    )
    holders, _ = parse_token_holders(_holders_html(row), contract=c)
    assert holders == []  # no /token/<c>?a=0x... link -> row skipped, no blank address
