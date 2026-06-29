# tests/unit/test_models_address.py
from basescan_scraper.models.address import (
    AddressProfile,
    InternalTransaction,
    NftTransfer,
    TokenTransfer,
    Transaction,
)
from basescan_scraper.models.common import Amount


def test_transaction_minimal():
    tx = Transaction(
        hash="0xb239798ab298435ae661f8693bdc9ba52c7f04bae796d7d99f1cb7d976e2140d",
        block=47819759,
        timestamp="2026-06-26T00:00:00Z",
        from_address="0x3ae6963e000000000000000000000000008fdfe02b5",
        to_address="0x71c7656ec7ab88b098defb751b7401b5f6d8976f",
        value=Amount.from_wei("11209130000000000", symbol="ETH"),
        method="Transfer",
        direction="in",
    )
    assert tx.hash.startswith("0x")
    assert tx.direction == "in"


def test_address_profile_minimal():
    p = AddressProfile(
        address="0x71c7656ec7ab88b098defb751b7401b5f6d8976f",
        eth_balance=Amount.from_wei("309061258262416160", symbol="ETH"),
        token_holdings_count=201,
    )
    assert p.address.startswith("0x")
    assert p.token_holdings_count == 201


def test_token_transfer_amount_is_string():
    t = TokenTransfer(hash="0x" + "a" * 64, block=1, from_address="0x" + "1" * 40,
                      to_address="0x" + "2" * 40, amount="382,277",
                      token_name="Eos", token_symbol="Eos", token_address="0x" + "3" * 40)
    assert t.amount == "382,277"
    assert t.token_symbol == "Eos"


def test_nft_transfer_has_type_and_quantity():
    n = NftTransfer(hash="0x" + "a" * 64, block=1, from_address="0x" + "1" * 40,
                    to_address="0x" + "2" * 40, token_type="ERC-1155",
                    token_id="6277", token_address="0x" + "3" * 40,
                    collection_name="SuperPositions", quantity="14526371714", method="Exec Transaction")
    assert n.token_type == "ERC-1155"
    assert n.quantity == "14526371714"


def test_internal_transaction_shape():
    i = InternalTransaction(parent_hash="0x" + "a" * 64, block=1, from_address="0x" + "1" * 40,
                            to_address="0x" + "2" * 40, value=Amount.from_wei("730000000000", symbol="ETH"))
    assert i.parent_hash.startswith("0x")
