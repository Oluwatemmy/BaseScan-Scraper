from pathlib import Path

from basescan_scraper.parsers.pagination import parse_pagination

FX = Path(__file__).parent.parent / "fixtures"


def test_parse_pagination_txs_p1():
    html = (FX / "txs_donate_p1.html").read_text(encoding="utf-8")
    total, pages = parse_pagination(html)
    assert total == 96
    assert pages == 2


def test_parse_pagination_token():
    html = (FX / "tokentxns_donate.html").read_text(encoding="utf-8")
    total, pages = parse_pagination(html)
    assert total == 402
    assert pages == 9


def test_parse_pagination_absent_defaults():
    total, pages = parse_pagination("<html>nothing</html>")
    assert total is None
    assert pages == 1
