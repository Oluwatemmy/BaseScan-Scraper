from pathlib import Path

from basescan_scraper.parsers.transaction import is_tx_not_found, _tx_iso_timestamp
from basescan_scraper.parsers.transaction import parse_event_logs
from basescan_scraper.parsers.transaction import parse_transaction_detail

FX = Path(__file__).parent.parent / "fixtures"


def test_tx_iso_timestamp_parses_tx_page_format():
    assert _tx_iso_timestamp("Jun-25-2026 11:07:45 PM +UTC") == "2026-06-25T23:07:45Z"
    assert _tx_iso_timestamp("Dec-14-2023 06:34:07 PM +UTC") == "2023-12-14T18:34:07Z"
    assert _tx_iso_timestamp("nope") is None


def test_is_tx_not_found():
    assert is_tx_not_found((FX / "tx_notfound.html").read_text(encoding="utf-8")) is True
    assert is_tx_not_found((FX / "tx_eth.html").read_text(encoding="utf-8")) is False


def test_parse_eth_tx_core():
    html = (FX / "tx_eth.html").read_text(encoding="utf-8")
    tx = parse_transaction_detail(html)
    assert tx.hash == "0xb239798ab298435ae661f8693bdc9ba52c7f04bae796d7d99f1cb7d976e2140d"
    assert tx.status == "success"
    assert tx.block == 47819759
    assert tx.timestamp == "2026-06-25T23:07:45Z"
    assert tx.from_address == "0x3ae6963e43f804e455b123c2015cfc88fdfe02b5"
    assert tx.to_address == "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"
    assert tx.value.decimal == "0.011209138199984949"
    assert tx.transaction_fee.decimal == "0.000000142838519275"
    assert tx.gas_price.decimal == "0.00675"
    assert tx.nonce == 3
    assert tx.token_transfers == []
    assert tx.input.raw_hex.startswith("0x")


def test_parse_token_tx_transfers():
    html = (FX / "tx_token.html").read_text(encoding="utf-8")
    tx = parse_transaction_detail(html)
    assert tx.block == 7894750
    assert len(tx.token_transfers) == 2
    t0 = tx.token_transfers[0]
    assert t0.from_address.startswith("0x") and len(t0.from_address) == 42
    assert t0.to_address.startswith("0x") and len(t0.to_address) == 42
    assert t0.amount  # non-empty display amount
    assert t0.token_address and len(t0.token_address) == 42
    # exact row-0 values read from tests/fixtures/tx_token.html
    assert t0.from_address == "0x36fd8c763152ee77f8481d56cadf027a6a0aefb3"
    assert t0.to_address == "0x580d2c2da4f58d9efc2fdb5982ea67edc9620258"
    assert t0.amount == "0.1"
    assert t0.token_symbol == "USDC"
    assert t0.token_name == "USDC"
    assert t0.token_address == "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"


def test_parse_event_logs():
    html = (FX / "tx_token.html").read_text(encoding="utf-8")
    logs = parse_event_logs(html)
    assert len(logs) >= 1
    log = logs[0]
    assert log.contract_address.startswith("0x") and len(log.contract_address) == 42
    assert isinstance(log.topics, list) and len(log.topics) >= 1
    assert all(t.startswith("0x") for t in log.topics)
    # exact values read from tests/fixtures/tx_token.html (logs logI_28..logI_32)
    assert len(logs) == 5
    assert log.log_index == 28
    assert log.contract_address == "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
    assert len(log.topics) == 1
    assert log.topics[0] == (
        "0xbc7cd75a20ee27fd9adebab32041f755214dbc6bffa90cc0225b39da2e5c2d3b"
    )
    assert log.data == (
        "0x0000000000000000000000002ce6311ddae708829bc0784c967b7d77d19fd779"
    )


def test_parse_event_logs_eth_tx_minimal():
    html = (FX / "tx_eth.html").read_text(encoding="utf-8")
    assert parse_event_logs(html) == []


def test_parse_contract_creation_tx():
    html = (FX / "tx_contract_creation.html").read_text(encoding="utf-8")
    tx = parse_transaction_detail(html)
    assert tx.status == "success"
    assert tx.to_address is None
    assert tx.contract_created == "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"


def test_is_contract_creation_marker():
    from selectolax.parser import HTMLParser

    from basescan_scraper.parsers.transaction import _is_contract_creation
    eth = HTMLParser((FX / "tx_eth.html").read_text(encoding="utf-8"))
    token = HTMLParser((FX / "tx_token.html").read_text(encoding="utf-8"))
    creation = HTMLParser((FX / "tx_contract_creation.html").read_text(encoding="utf-8"))
    assert _is_contract_creation(eth) is False
    assert _is_contract_creation(token) is False
    assert _is_contract_creation(creation) is True


def test_parse_contract_call_to_address():
    # contract-call tx labels the recipient "Interacted With (To)", not "To"
    html = (FX / "tx_token.html").read_text(encoding="utf-8")
    tx = parse_transaction_detail(html)
    assert tx.to_address == "0x36fd8c763152ee77f8481d56cadf027a6a0aefb3"
