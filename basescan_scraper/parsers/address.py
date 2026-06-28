# basescan_scraper/parsers/address.py
import re

from selectolax.parser import HTMLParser

from basescan_scraper.models.address import AddressProfile, Transaction
from basescan_scraper.models.common import Amount
from basescan_scraper.parsers.common import (
    ParseError,
    clean_text,
    parse_wei_from_eth_text,
)

_HOLDINGS_RE = re.compile(r"\(>?(\d[\d,]*)\s+Tokens\)")
_HOLDINGS_USD_RE = re.compile(r">?\$([\d,]+(?:\.\d+)?)\s*\(>?\d[\d,]*\s+Tokens\)")
_HASH_RE = re.compile(r"/tx/(0x[0-9a-fA-F]{64})")
_ADDR_RE = re.compile(r"^0x[0-9a-f]{40}$")
_FUNDED_BY_RE = re.compile(
    r"Funded By.*?/address/(0x[0-9a-fA-F]{40})", re.DOTALL
)
_USD_RE = re.compile(r"\$([\d,]+(?:\.\d+)?)")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")


def _find_label_value(tree: HTMLParser, label: str) -> str | None:
    """Find the text of the element following a label like 'ETH Balance'."""
    for node in tree.css("h4, .card-body h4, div"):
        if clean_text(node.text(deep=True)).lower() == label.lower():
            sib = node.next
            while sib is not None and not clean_text(sib.text(deep=True)):
                sib = sib.next
            if sib is not None:
                return clean_text(sib.text(deep=True))
    return None


def parse_address_profile(html: str, address: str) -> AddressProfile:
    tree = HTMLParser(html)

    balance_text = _find_label_value(tree, "ETH Balance")
    if balance_text is None:
        raise ParseError("address page missing 'ETH Balance' — possible HTML drift")
    eth_balance = Amount.from_wei(parse_wei_from_eth_text(balance_text), symbol="ETH")

    holdings_count = None
    holdings_value_usd = None
    for node in tree.css("*"):
        txt = clean_text(node.text(deep=True))
        if "Tokens)" in txt and "$" in txt:
            m = _HOLDINGS_RE.search(txt)
            if m:
                holdings_count = int(m.group(1).replace(",", ""))
            usd_m = _HOLDINGS_USD_RE.search(txt)
            if usd_m:
                holdings_value_usd = usd_m.group(1).replace(",", "")
            break

    eth_value_usd = None
    eth_value_text = _find_label_value(tree, "ETH Value")
    if eth_value_text:
        usd_m = _USD_RE.search(eth_value_text)
        if usd_m:
            eth_value_usd = usd_m.group(1).replace(",", "")

    funded_by = None
    funded_m = _FUNDED_BY_RE.search(html)
    if funded_m:
        funded_by = funded_m.group(1).lower()

    return AddressProfile(
        address=address.lower(),
        eth_balance=eth_balance,
        eth_value_usd=eth_value_usd,
        token_holdings_count=holdings_count,
        token_holdings_value_usd=holdings_value_usd,
        funded_by=funded_by,
    )


def _transactions_table(tree: HTMLParser):
    container = tree.css_first("#transactions")
    if container is None:
        return None
    return container.css_first("table")


def _row_addresses(tr) -> list[str]:
    """Collect the row's From/To addresses in document order. A party appears
    either as a `data-highlight-target` attribute (nametagged cells like
    "BaseScan: Donate") OR as an `/address/0x...` href (ENS/domain-named cells
    like "oxmax.base.eth", which carry no data-highlight-target). We read both
    so an ENS-named counterparty is never dropped. Lowercased, validated,
    order-preserving dedup; first = from, second = to."""
    ordered: list[str] = []

    def _add(val: str | None) -> None:
        if not val:
            return
        val = val.lower()
        if _ADDR_RE.match(val) and val not in ordered:
            ordered.append(val)

    # Walk ALL descendants in document order (a comma selector groups matches by
    # selector, not document order, which would swap From/To). For each node take
    # its data-highlight-target, else an /address/ href.
    for n in tr.css("*"):
        dht = n.attributes.get("data-highlight-target")
        if dht:
            _add(dht)
            continue
        href = n.attributes.get("href") or ""
        m = re.search(r"/address/(0x[0-9a-fA-F]{40})", href)
        if m:
            _add(m.group(1))
    return ordered


def _row_value_wei(tr) -> str:
    """Parse the ETH value from the `span.td_showAmount` element specifically,
    avoiding the hidden USD span in the same cell. Falls back to '0'."""
    amount_node = tr.css_first("span.td_showAmount")
    if amount_node is None:
        return "0"
    try:
        return parse_wei_from_eth_text(clean_text(amount_node.text(deep=True)))
    except ValueError:
        return "0"


def _row_method(tr) -> str | None:
    """Read the Action/method badge from the visible function-name cell."""
    cell = tr.css_first("td.td_functionNameOri")
    if cell is None:
        return None
    text = clean_text(cell.text(deep=True))
    return text or None


def _row_timestamp(tr) -> str | None:
    """Convert the hidden showDate cell ('YYYY-MM-DD HH:MM:SS') to ISO 8601 UTC."""
    cell = tr.css_first("td.showDate")
    if cell is None:
        return None
    text = clean_text(cell.text(deep=True))
    if not _DATE_RE.match(text):
        return None
    return text.replace(" ", "T") + "Z"


def _row_txn_fee(tr) -> Amount | None:
    """Parse the Txn Fee cell (plain ETH number) into an Amount, or None."""
    cell = tr.css_first("td.showTxnFee")
    if cell is None:
        return None
    text = clean_text(cell.text(deep=True))
    try:
        return Amount.from_wei(parse_wei_from_eth_text(text), symbol="ETH")
    except ValueError:
        return None


def parse_transactions(html: str) -> list[Transaction]:
    tree = HTMLParser(html)
    table = _transactions_table(tree)
    if table is None:
        return []

    rows: list[Transaction] = []
    for tr in table.css("tbody tr"):
        row_html = tr.html or ""
        hash_m = _HASH_RE.search(row_html)
        if not hash_m:
            continue
        addrs = _row_addresses(tr)
        from_addr = addrs[0] if addrs else ""
        to_addr = addrs[1] if len(addrs) > 1 else None

        block_m = re.search(r"/block/(\d+)", row_html)
        block = int(block_m.group(1)) if block_m else 0

        direction = None
        for cell in tr.css("td"):
            t = clean_text(cell.text(deep=True)).upper()
            if t in {"IN", "OUT", "SELF"}:
                direction = t.lower()
                break

        value_wei = _row_value_wei(tr)

        rows.append(
            Transaction(
                hash=hash_m.group(1),
                block=block,
                timestamp=_row_timestamp(tr),
                from_address=from_addr,
                to_address=to_addr,
                value=Amount.from_wei(value_wei, symbol="ETH"),
                method=_row_method(tr),
                direction=direction,
                txn_fee=_row_txn_fee(tr),
            )
        )
    return rows
