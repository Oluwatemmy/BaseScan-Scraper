# basescan_scraper/models/address.py
from typing import Literal, Optional

from pydantic import BaseModel, Field

from basescan_scraper.models.common import Amount

Direction = Literal["in", "out", "self"]


class Transaction(BaseModel):
    hash: str = Field(examples=["0xb239798ab2…2140d"])
    block: int = Field(examples=[47819759])
    timestamp: Optional[str] = Field(default=None, description="ISO 8601 UTC")
    from_address: str = Field(examples=["0x3ae6963e…02b5"])
    to_address: Optional[str] = Field(default=None, description="None for contract creation")
    value: Amount
    method: Optional[str] = Field(default=None, examples=["Transfer"])
    direction: Optional[Direction] = Field(default=None)
    txn_fee: Optional[Amount] = Field(default=None)


class InternalTransaction(BaseModel):
    parent_hash: str
    block: int
    timestamp: Optional[str] = None
    from_address: str
    to_address: Optional[str] = None
    value: Amount


class TokenTransfer(BaseModel):
    hash: str
    block: int
    timestamp: Optional[str] = None
    from_address: str
    to_address: str
    value: Amount
    token_name: Optional[str] = None
    token_symbol: Optional[str] = None
    token_address: Optional[str] = None


class NftTransfer(BaseModel):
    hash: str
    block: int
    timestamp: Optional[str] = None
    from_address: str
    to_address: str
    token_id: Optional[str] = None
    collection_name: Optional[str] = None
    token_address: Optional[str] = None


class AddressProfile(BaseModel):
    address: str
    eth_balance: Amount
    eth_value_usd: Optional[str] = Field(default=None, examples=["484.64"])
    token_holdings_count: Optional[int] = Field(default=None, examples=[201])
    token_holdings_value_usd: Optional[str] = Field(default=None, examples=["71123407.61"])
    funded_by: Optional[str] = Field(default=None)
    is_contract: bool = False
