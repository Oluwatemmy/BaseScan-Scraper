from basescan_scraper.models.common import Amount
from basescan_scraper.models.transaction import (
    EventLog, InputData, TransactionDetail, TxTokenTransfer,
)


def test_transaction_detail_minimal():
    tx = TransactionDetail(
        hash="0x" + "a" * 64, status="success", block=1, from_address="0x" + "1" * 40,
        value=Amount.from_wei("0", symbol="ETH"),
        transaction_fee=Amount.from_wei("0", symbol="ETH"),
        gas_price=Amount.from_wei("0", decimals=9, symbol="Gwei"),
        gas_limit=21000, gas_used=21000, input=InputData(raw_hex="0x"),
    )
    assert tx.status == "success"
    assert tx.to_address is None and tx.token_transfers == []


def test_tx_token_transfer_and_log():
    t = TxTokenTransfer(from_address="0x" + "1" * 40, to_address="0x" + "2" * 40,
                        amount="9", token_symbol="QUID", token_address="0x" + "3" * 40)
    assert t.amount == "9"
    log = EventLog(contract_address="0x" + "3" * 40, topics=["0xabc"], data="0x")
    assert log.topics == ["0xabc"]
