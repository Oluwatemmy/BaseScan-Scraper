import re
from datetime import datetime, timezone

from selectolax.parser import HTMLParser

from basescan_scraper.models.common import Amount
from basescan_scraper.models.transaction import (
    EventLog,
    InputData,
    TransactionDetail,
    TxTokenTransfer,
)
from basescan_scraper.parsers.common import (
    ParseError,
    clean_text,
    parse_wei_from_eth_text,
)

# tx page timestamp text: "Jun-25-2026 11:07:45 PM +UTC".
# BaseScan always renders the tx timestamp with a "+UTC" suffix, so the parser
# treats the parsed wall-clock time as UTC.
_TX_DT_RE = re.compile(r"([A-Z][a-z]{2}-\d{2}-\d{4} \d{1,2}:\d{2}:\d{2} [AP]M)")

_NONCE_RE = re.compile(r"Nonce:\s*</span>\s*(\d+)")
# "21,000 | 21,000 (100%)"
_GAS_LIMIT_USAGE_RE = re.compile(
    r"([\d,]+)\s*\|\s*([\d,]+)\s*(?:\(([\d.]+%)\))?"
)
# "21,000 (100%)"
_GAS_USED_RE = re.compile(r"([\d,]+)\s*(?:\(([\d.]+%)\))?")


def _tx_iso_timestamp(text: str | None) -> str | None:
    if not text:
        return None
    m = _TX_DT_RE.search(text)
    if not m:
        return None
    try:
        dt = datetime.strptime(m.group(1), "%b-%d-%Y %I:%M:%S %p").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def is_tx_not_found(html: str) -> bool:
    """A valid /tx page has #spanTxHash; the not-found page does not."""
    return HTMLParser(html).css_first("#spanTxHash") is None


def _find_label_row(tree: HTMLParser, label: str):
    """Find the overview row (a `.row` ancestor) whose label cell text equals
    `label` (e.g. 'From', 'To'). Returns the row node or None."""
    for node in tree.css("div"):
        if node.text(deep=False).strip().rstrip(":") == label:
            row = node
            for _ in range(5):
                if row is None:
                    break
                cls = row.attributes.get("class") or ""
                if "row" in cls.split():
                    break
                row = row.parent
            return row
    return None


def _row_address(tree: HTMLParser, label: str) -> str | None:
    """Find the overview row whose label cell text equals `label` (e.g. 'From')
    and return the lowercased /address/0x… link target within that row."""
    row = _find_label_row(tree, label)
    if row is None:
        return None
    link = row.css_first('a[href^="/address/0x"]')
    if link is None:
        return None
    href = link.attributes.get("href") or ""
    m = re.search(r"/address/(0x[0-9a-fA-F]{40})", href)
    return m.group(1).lower() if m else None


def _is_contract_creation(tree: HTMLParser) -> bool:
    """Return True when the transaction created a contract.

    For a contract-creation tx, BaseScan renders the recipient ("To") row as
    "[ <icon> 0x… Created ]" — the address there is the newly-created contract
    rather than a normal recipient. The robust marker is the word "Created" in
    the recipient row's text.
    """
    row = _find_label_row(tree, "To")
    if row is None:
        return False
    return "Created" in row.text(deep=True)


def _amount_from_node(
    tree: HTMLParser, selector: str, *, decimals: int = 18, symbol: str = "ETH"
) -> Amount:
    """Extract an Amount from an ETH-text node; default to 0 if missing/malformed."""
    node = tree.css_first(selector)
    if node is None:
        return Amount.from_wei("0", decimals=decimals, symbol=symbol)
    try:
        wei = parse_wei_from_eth_text(clean_text(node.text(deep=True)), decimals=decimals)
    except ValueError:
        return Amount.from_wei("0", decimals=decimals, symbol=symbol)
    return Amount.from_wei(wei, decimals=decimals, symbol=symbol)


def _map_status(text: str) -> str:
    low = text.lower()
    if "success" in low:
        return "success"
    if "fail" in low:
        return "failed"
    return clean_text(text).lower() or "unknown"


# token link text like "ERC-20: Name (SYM)" or "Name (SYM)"
_TOKEN_NAME_SYM_RE = re.compile(r"(?:ERC-\d+:\s*)?(.+)\s*\(([^)]+)\)\s*$")
_HREF_TOKEN_A_RE = re.compile(r"/token/0x[0-9a-fA-F]{40}\?a=(0x[0-9a-fA-F]{40})")
_HREF_TOKEN_RE = re.compile(r"/token/(0x[0-9a-fA-F]{40})")


def _parse_tx_token_transfers(tree: HTMLParser) -> list[TxTokenTransfer]:
    """Parse the ERC-20 'Tokens Transferred' section of a /tx page.

    Each transfer is a `div.row-count` inside the #nav_pane_erc20_transfer
    pane and renders: From <addr>, To <addr>, an amount, and a token link.
    From/To addresses live in the `?a=0x…` query of `/token/…` links; the
    token link without `?a=` carries the token address and "Name (SYM)" text.
    Malformed transfers are skipped rather than raising.
    """
    pane = tree.css_first("#nav_pane_erc20_transfer")
    if pane is None:
        return []

    transfers: list[TxTokenTransfer] = []
    for row in pane.css("div.row-count"):
        try:
            # From (1st) / To (2nd): address is the ?a= param of /token/ links.
            addrs: list[str] = []
            for a in row.css('a[href*="/token/"]'):
                href = a.attributes.get("href") or ""
                m = _HREF_TOKEN_A_RE.search(href)
                if m:
                    addrs.append(m.group(1).lower())
            if len(addrs) < 2:
                continue
            from_address, to_address = addrs[0], addrs[1]

            # amount: the span carrying the "Current Price" tooltip.
            amount = ""
            for span in row.css("span[title]"):
                if (span.attributes.get("title") or "").startswith("Current Price"):
                    amount = clean_text(span.text(deep=False))
                    break

            # token link (the /token/0x… link WITHOUT a ?a= query).
            token_address = None
            token_name = None
            token_symbol = None
            for a in row.css('a[href*="/token/"]'):
                href = a.attributes.get("href") or ""
                if "?a=" in href:
                    continue
                tm = _HREF_TOKEN_RE.search(href)
                if not tm:
                    continue
                token_address = tm.group(1).lower()
                label = clean_text(a.text(deep=True))
                nm = _TOKEN_NAME_SYM_RE.match(label)
                if nm:
                    token_name = nm.group(1).strip() or None
                    token_symbol = nm.group(2).strip() or None
                elif label:
                    token_name = label
                break

            transfers.append(
                TxTokenTransfer(
                    from_address=from_address,
                    to_address=to_address,
                    amount=amount,
                    token_name=token_name,
                    token_symbol=token_symbol,
                    token_address=token_address,
                )
            )
        except Exception:
            # Degrade gracefully: skip a malformed transfer rather than crash.
            continue

    return transfers


# topic0 is a direct 32-byte hex; indexed topics 1+ render as address links but
# carry the full padded 32-byte topic in a `funcDecodeOnclick1('Hex', '..', '0x..')`
# dropdown. This pulls the 0x-prefixed hex out of that JS call.
_TOPIC_HEX_DECODE_RE = re.compile(
    r"funcDecodeOnclick1\(\s*'Hex'\s*,\s*'[^']*'\s*,\s*'(0x[0-9a-fA-F]+)'"
)
_LOG_INDEX_RE = re.compile(r"logI_(\d+)")
_HEX_32_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")


def _log_topics(block: HTMLParser) -> list[str]:
    """Extract ordered topic hex strings from a log block's Topics section.

    topic0 is a plain 32-byte hex in a `span.font-monospace.text-break`; indexed
    topics render as address links but expose their padded 32-byte value in a
    `funcDecodeOnclick1('Hex', …, '0x…')` dropdown. Each topic `<li>` yields one
    topic; the inner HTML is searched for whichever form is present.
    """
    topics: list[str] = []
    # Find the Topics <dl>: its <dt> text contains "Topics".
    for dl in block.css("dl"):
        dt = dl.css_first("dt")
        if dt is None or "Topics" not in dt.text(deep=True):
            continue
        for li in dl.css("li"):
            # Prefer the explicit Hex dropdown (indexed topics).
            inner = li.html or ""
            m = _TOPIC_HEX_DECODE_RE.search(inner)
            if m:
                topics.append(m.group(1).lower())
                continue
            # Otherwise a direct 32-byte hex span (topic0).
            for span in li.css("span.font-monospace"):
                txt = clean_text(span.text(deep=True))
                if _HEX_32_RE.match(txt):
                    topics.append(txt.lower())
                    break
        break
    return topics


def parse_event_logs(html: str) -> list[EventLog]:
    """Parse the Transaction Receipt Event Logs of a BaseScan /tx page.

    Each log is a `div[id^="logI_"]` block carrying an Address (the emitting
    contract), a numeric log index (from the `logI_<n>` id), an ordered list of
    Topics, and a raw Data hex blob. Returns ``[]`` when the page has no logs
    (e.g. a plain ETH transfer). Malformed log blocks are skipped rather than
    raising.
    """
    tree = HTMLParser(html)
    logs: list[EventLog] = []
    for block in tree.css('div[id^="logI_"]'):
        try:
            block_id = block.attributes.get("id") or ""
            im = _LOG_INDEX_RE.search(block_id)
            log_index = int(im.group(1)) if im else None

            link = block.css_first('a[href^="/address/0x"]')
            if link is None:
                continue
            href = link.attributes.get("href") or ""
            am = re.search(r"/address/(0x[0-9a-fA-F]{40})", href)
            if not am:
                continue
            contract_address = am.group(1).lower()

            topics = _log_topics(block)

            data = "0x"
            raw = block.css_first('div[id^="event_raw_data_"]')
            if raw is not None:
                data = clean_text(raw.text(deep=True)) or "0x"

            logs.append(
                EventLog(
                    log_index=log_index,
                    contract_address=contract_address,
                    topics=topics,
                    data=data,
                )
            )
        except Exception:
            # Degrade gracefully: skip a malformed log block rather than crash.
            continue
    return logs


def parse_transaction_detail(html: str) -> TransactionDetail:
    """Parse a BaseScan /tx detail page into a TransactionDetail.

    Only the hash being absent is fatal (raises ParseError); all other optional
    fields degrade to None / sensible defaults rather than raising.
    """
    tree = HTMLParser(html)

    hash_node = tree.css_first("#spanTxHash")
    if hash_node is None:
        raise ParseError("tx page missing #spanTxHash")
    tx_hash = clean_text(hash_node.text(deep=True))

    # status
    status = "unknown"
    status_node = tree.css_first("#data-status")
    if status_node is not None:
        status = _map_status(status_node.text(deep=True))

    # block
    block = 0
    bm = re.search(r"/block/(\d+)", html)
    if bm:
        block = int(bm.group(1))

    # timestamp
    timestamp = None
    date_node = tree.css_first("#showUtcLocalDate")
    if date_node is not None:
        timestamp = _tx_iso_timestamp(clean_text(date_node.text(deep=True)))

    # from / to. The recipient row is "To" (plain transfer), "Interacted With (To)"
    # (contract call), or "[ Contract 0x… Created ]" (contract creation). For a
    # creation, the /address/ link is the newly-created contract, not a recipient.
    from_address = _row_address(tree, "From") or ""
    to_address = None
    contract_created = None
    recipient = _row_address(tree, "To") or _row_address(tree, "Interacted With (To)")
    if recipient is not None:
        if _is_contract_creation(tree):
            contract_created = recipient
        else:
            to_address = recipient

    # value / fee (ETH, 18 decimals); gas price (Gwei, 9 decimals).
    value = _amount_from_node(tree, "#ContentPlaceHolder1_spanValue")
    transaction_fee = _amount_from_node(tree, "#ContentPlaceHolder1_spanTxFee")
    gas_price = _amount_from_node(
        tree, "#ContentPlaceHolder1_spanGasPrice", decimals=9, symbol="Gwei"
    )

    # gas limit / gas used / pct
    gas_limit = 0
    gas_used = 0
    gas_used_pct = None
    gu_node = tree.css_first("#ContentPlaceHolder1_spanGasUsedByTxn")
    if gu_node is not None:
        # The enclosing cell renders "<limit> | <used> (<pct>)"; the divider span
        # separates the gas-limit span from the gas-used span.
        cell = gu_node.parent
        cell_text = clean_text(cell.text(deep=True)) if cell is not None else ""
        m = _GAS_LIMIT_USAGE_RE.search(cell_text)
        if m:
            gas_limit = int(m.group(1).replace(",", ""))
            gas_used = int(m.group(2).replace(",", ""))
            gas_used_pct = m.group(3)
        else:
            gu_text = clean_text(gu_node.text(deep=True))
            m = _GAS_USED_RE.search(gu_text)
            if m:
                gas_used = int(m.group(1).replace(",", ""))
                gas_used_pct = m.group(2)

    # nonce
    nonce = None
    nm = _NONCE_RE.search(html)
    if nm:
        nonce = int(nm.group(1))

    # method / transaction action function name
    method = None
    mn = tree.css_first("#ContentPlaceHolder1_spanFunctionName")
    if mn is not None:
        method = clean_text(mn.text(deep=True)) or None

    # input data
    raw_hex = "0x"
    decoded = None
    raw_node = tree.css_first("#rawinput")
    if raw_node is not None:
        raw_hex = clean_text(raw_node.text(deep=True)) or "0x"
    dec_node = tree.css_first("#inputDecode")
    if dec_node is not None:
        decoded = clean_text(dec_node.text(deep=True)) or None
    method_id = raw_hex[:10] if len(raw_hex) > 2 else None
    input_data = InputData(method_id=method_id, decoded=decoded, raw_hex=raw_hex)

    return TransactionDetail(
        hash=tx_hash,
        status=status,
        block=block,
        timestamp=timestamp,
        from_address=from_address,
        to_address=to_address,
        contract_created=contract_created,
        value=value,
        transaction_fee=transaction_fee,
        gas_price=gas_price,
        gas_limit=gas_limit,
        gas_used=gas_used,
        gas_used_pct=gas_used_pct,
        nonce=nonce,
        method=method,
        token_transfers=_parse_tx_token_transfers(tree),
        input=input_data,
    )
