import re

from selectolax.parser import HTMLParser

from basescan_scraper.models.token import TokenHolder, TokenInfo
from basescan_scraper.parsers.common import ParseError, clean_text

__all__ = [
    "TokenHolder",
    "TokenInfo",
    "is_token_not_found",
    "parse_token_holders",
    "parse_token_info",
]

_TITLE_RE = re.compile(r"(.+?)\s*\(([^)]+)\)\s*\|\s*(ERC-\d+)")
_PRICE_RE = re.compile(r"Price:\s*\$([\d.,]+)")
_MCAP_RE = re.compile(r"Onchain Market Cap:\s*\$([\d,]+\.?\d*)")
_HOLDERS_RE = re.compile(r"Holders:\s*([\d,]+)")
_MAXSUPPLY_RE = re.compile(r"Max Total Supply\s*([\d,]+\.?\d*)")
_DECIMALS_RE = re.compile(r"WITH\s*(\d+)\s*Decimals")
_TOP_RE = re.compile(r"Top ([\d,]+) holders\s*(?:<[^>]+>)?\s*\(?\s*From a total of")


def _looks_like_address(text: str) -> bool:
    """True when the label cell is just an address display (e.g. '0x1234...5678'
    or a full 0x… address), not a real nametag. A genuine label such as
    '0xVault' keeps non-hex characters and is NOT treated as an address."""
    if not text.lower().startswith("0x"):
        return False
    core = text[2:].replace("...", "").replace("…", "").replace(" ", "")
    return bool(core) and all(c in "0123456789abcdefABCDEF" for c in core)


def is_token_not_found(html: str) -> bool:
    """A valid ERC-20 token page has a 'Name (SYM) | ERC-20' title AND a
    '(WITH N Decimals)' marker. The not-found / non-ERC-20 page has neither."""
    tree = HTMLParser(html)
    title_node = tree.css_first("title")
    title = clean_text(title_node.text(deep=True)) if title_node else ""
    return _TITLE_RE.match(title) is None or "Decimals)" not in html


def parse_token_info(html: str, address: str) -> TokenInfo:
    if is_token_not_found(html):
        raise ParseError("not a valid ERC-20 token page")
    tree = HTMLParser(html)
    title = clean_text(tree.css_first("title").text(deep=True))
    tm = _TITLE_RE.match(title)
    name = symbol = type_ = None
    if tm:
        name, symbol, type_ = tm.group(1), tm.group(2), tm.group(3)

    def _grp(rx):
        m = rx.search(html)
        return m.group(1) if m else None

    price = _grp(_PRICE_RE)
    mcap = _grp(_MCAP_RE)
    holders = _grp(_HOLDERS_RE)
    holders_count = int(holders.replace(",", "")) if holders else None

    # Max Total Supply: the hidden input carries the exact value without the
    # inline <b>.</b> markup that splits the visible span.
    max_supply = None
    hidden = tree.css_first("input#ContentPlaceHolder1_hdnTotalSupply")
    if hidden:
        attr = hidden.attributes.get("value")
        max_supply = clean_text(attr) if attr else None

    # Decimals: 'Token Contract (WITH <b>6</b> Decimals)'. On cleaned body text
    # the inline <b> tags collapse, yielding 'WITH 6 Decimals'.
    page_text = clean_text(tree.body.text(deep=True)) if tree.body else ""
    if max_supply is None:
        sup_m = _MAXSUPPLY_RE.search(page_text)
        max_supply = sup_m.group(1) if sup_m else None
    dec_m = _DECIMALS_RE.search(page_text)
    decimals = int(dec_m.group(1)) if dec_m else None

    return TokenInfo(
        address=address.lower(), name=name, symbol=symbol, type=type_,
        decimals=decimals, price_usd=price, max_total_supply=max_supply,
        holders_count=holders_count, market_cap_usd=mcap,
    )


def _holders_table(tree):
    for t in tree.css("table"):
        heads = [clean_text(th.text(deep=True)) for th in t.css("thead th")]
        if "Quantity" in heads and "Rank" in heads:
            return t
    return None


def parse_token_holders(html: str, contract: str) -> tuple[list[TokenHolder], int | None]:
    tree = HTMLParser(html)
    table = _holders_table(tree)
    if table is None:
        return [], None
    # Allow other query params before 'a=' (e.g. /token/<c>?sid=…&a=0x…), not
    # only '?a=' immediately after the path. The \b before 'a=' anchors to a
    # param boundary ('&'/'&amp;'/'?') and avoids matching 'data='/'xa='.
    addr_re = re.compile(
        rf"/token/{contract.lower()}\?[^\"'>]*?\ba=(0x[0-9a-fA-F]{{40}})", re.I)
    holders: list[TokenHolder] = []
    for tr in table.css("tbody tr"):
        cells = tr.css("td")
        if len(cells) < 6:
            continue
        try:
            rank = int(clean_text(cells[0].text(deep=True)))
        except ValueError:
            continue
        am = addr_re.search(tr.html or "")
        if am is None:
            continue  # no parseable holder address -> skip, don't emit a blank one
        address = am.group(1).lower()
        label_text = clean_text(cells[1].text(deep=True)).replace("Copy Address", "").strip()
        label = label_text if (label_text and not _looks_like_address(label_text)) else None
        quantity = clean_text(cells[3].text(deep=True))
        # cells[4] (Percentage) is a JS-filled "0.0000%" placeholder on the
        # server HTML — not parsed here; the service computes it from supply.
        value_raw = clean_text(cells[5].text(deep=True))
        value_usd = value_raw.replace("$", "").strip() or None
        holders.append(TokenHolder(rank=rank, address=address, label=label,
                                   quantity=quantity, value_usd=value_usd))
    tot_m = _TOP_RE.search(html)
    total = int(tot_m.group(1).replace(",", "")) if tot_m else None
    return holders, total
