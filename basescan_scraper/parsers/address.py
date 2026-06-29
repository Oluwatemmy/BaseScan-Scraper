# basescan_scraper/parsers/address.py
import re

from selectolax.parser import HTMLParser

from basescan_scraper.models.address import (
    AddressProfile,
    InternalTransaction,
    TokenTransfer,
    Transaction,
)
from basescan_scraper.models.common import Amount
from basescan_scraper.parsers.common import (
    ParseError,
    clean_text,
    parse_wei_from_eth_text,
    to_iso_utc,
)

_HOLDINGS_RE = re.compile(r"\(>?(\d[\d,]*)\s+Tokens\)")
_HOLDINGS_USD_RE = re.compile(r">?\$([\d,]+(?:\.\d+)?)\s*\(>?\d[\d,]*\s+Tokens\)")
_HASH_RE = re.compile(r"/tx/(0x[0-9a-fA-F]{64})")
_ADDR_RE = re.compile(r"^0x[0-9a-f]{40}$")
_FUNDED_BY_RE = re.compile(
    r"Funded By.*?/address/(0x[0-9a-fA-F]{40})", re.DOTALL
)
_USD_RE = re.compile(r"\$([\d,]+(?:\.\d+)?)")
_TOKEN_HREF_RE = re.compile(r"/token/(0x[0-9a-fA-F]{40})")
# Token cell text is "ERC-20: Name (SYM)" for most tokens, but well-known tokens
# (e.g. USDC) render as just "Name (SYM)" with no "ERC-20:" prefix — so it's optional.
_TOKEN_NAMESYM_RE = re.compile(r"(?:ERC-\d+:\s*)?(.+)\s*\(([^)]+)\)\s*$")


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

    is_contract = tree.css_first("#ContentPlaceHolder1_li_contracts") is not None

    return AddressProfile(
        address=address.lower(),
        eth_balance=eth_balance,
        eth_value_usd=eth_value_usd,
        token_holdings_count=holdings_count,
        token_holdings_value_usd=holdings_value_usd,
        funded_by=funded_by,
        is_contract=is_contract,
    )


def _transactions_table(tree: HTMLParser):
    """Prefer the #transactions container (the /address page); otherwise the first
    table that contains a /tx/ link (the dedicated /txs list page)."""
    container = tree.css_first("#transactions")
    if container is not None:
        table = container.css_first("table")
        if table is not None:
            return table
    for table in tree.css("table"):
        if table.css_first("a[href^='/tx/']") is not None:
            return table
    return None


def _row_addresses(tr) -> list[str]:
    """Collect the row's From/To addresses in document order. A party appears
    either as a `data-highlight-target` attribute (nametagged cells like
    "BaseScan: Donate" on the /address page), as an `/address/0x...` href
    (ENS/domain-named cells like "oxmax.base.eth", which carry no
    data-highlight-target), or — on the dedicated /txs list page — only as the
    `data-clipboard-text` of a copy button (a nametagged To cell there has
    neither a highlight target nor an /address/ href). We read all three so a
    counterparty is never dropped. Lowercased, validated, order-preserving
    dedup; first = from, second = to."""
    ordered: list[str] = []

    def _add(val: str | None) -> None:
        if not val:
            return
        val = val.lower()
        if _ADDR_RE.match(val) and val not in ordered:
            ordered.append(val)

    # Walk ALL descendants in document order (a comma selector groups matches by
    # selector, not document order, which would swap From/To). For each node take
    # its data-highlight-target, else an /address/ href, else a copy button's
    # data-clipboard-text (the only address carrier for a nametagged /txs To cell).
    for n in tr.css("*"):
        dht = n.attributes.get("data-highlight-target")
        if dht:
            _add(dht)
            continue
        href = n.attributes.get("href") or ""
        m = re.search(r"/address/(0x[0-9a-fA-F]{40})", href)
        if m:
            _add(m.group(1))
            continue
        _add(n.attributes.get("data-clipboard-text"))
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
    """ISO 8601 UTC from the hidden showDate cell ('YYYY-MM-DD H:MM:SS')."""
    cell = tr.css_first("td.showDate")
    if cell is None:
        return None
    return to_iso_utc(clean_text(cell.text(deep=True)))


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


def parse_internal_transactions(html: str) -> list[InternalTransaction]:
    tree = HTMLParser(html)
    table = None
    for t in tree.css("table"):
        if t.css_first("a[href^='/tx/']") is not None:
            table = t
            break
    if table is None:
        return []
    rows: list[InternalTransaction] = []
    for tr in table.css("tbody tr"):
        row_html = tr.html or ""
        hash_m = _HASH_RE.search(row_html)
        if not hash_m:
            continue
        addrs = _row_addresses(tr)
        block_m = re.search(r"/block/(\d+)", row_html)
        value_wei = _row_value_wei(tr)
        rows.append(
            InternalTransaction(
                parent_hash=hash_m.group(1),
                block=int(block_m.group(1)) if block_m else 0,
                timestamp=_row_timestamp(tr),
                from_address=addrs[0] if addrs else "",
                to_address=addrs[1] if len(addrs) > 1 else None,
                value=Amount.from_wei(value_wei, symbol="ETH"),
            )
        )
    return rows


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


def _token_cell(tr):
    """The Token column: the <td> containing a /token/ contract link. Keying off the
    link (not 'ERC-' text) means well-known tokens like USDC — which render as
    "USDC (USDC)" without the "ERC-20:" prefix — are still found."""
    for td in tr.css("td"):
        if _TOKEN_HREF_RE.search(td.html or ""):
            return td
    return None


def parse_token_transfers(html: str) -> list[TokenTransfer]:
    tree = HTMLParser(html)
    table = None
    for t in tree.css("table"):
        if t.css_first("a[href^='/tx/']") is not None:
            table = t
            break
    if table is None:
        return []
    rows: list[TokenTransfer] = []
    for tr in table.css("tbody tr"):
        row_html = tr.html or ""
        hash_m = _HASH_RE.search(row_html)
        if not hash_m:
            continue
        block_m = re.search(r"/block/(\d+)", row_html)
        amount_node = tr.css_first("span.td_showAmount")
        amount = clean_text(amount_node.text(deep=True)) if amount_node is not None else ""

        token_name = token_symbol = token_address = None
        tcell = _token_cell(tr)
        if tcell is not None:
            href_m = _TOKEN_HREF_RE.search(tcell.html or "")
            if href_m:
                token_address = href_m.group(1).lower()
            ns_m = _TOKEN_NAMESYM_RE.search(clean_text(tcell.text(deep=True)))
            if ns_m:
                # Greedy name group can absorb the space before '(', so strip it.
                token_name, token_symbol = ns_m.group(1).strip(), ns_m.group(2).strip()

        # Exclude the token CONTRACT address (from the Token cell) so it can never be
        # mistaken for from/to, regardless of column order.
        addrs = [a for a in _row_addresses(tr) if a != token_address]
        from_addr = addrs[0] if addrs else ""
        to_addr = addrs[1] if len(addrs) > 1 else (addrs[0] if addrs else "")

        rows.append(
            TokenTransfer(
                hash=hash_m.group(1),
                block=int(block_m.group(1)) if block_m else 0,
                timestamp=_row_timestamp(tr),
                from_address=from_addr,
                to_address=to_addr,
                amount=amount,
                token_name=token_name,
                token_symbol=token_symbol,
                token_address=token_address,
            )
        )
    return rows
