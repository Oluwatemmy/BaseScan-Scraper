from typing import Optional

from pydantic import BaseModel, Field

from basescan_scraper.models.common import Amount


class TxTokenTransfer(BaseModel):
    from_address: str
    to_address: str
    amount: str = Field(examples=["382,277"], description="Display amount as shown by BaseScan")
    token_name: Optional[str] = None
    token_symbol: Optional[str] = None
    token_address: Optional[str] = None


class InputData(BaseModel):
    method_id: Optional[str] = Field(default=None, examples=["0xa9059cbb"])
    decoded: Optional[str] = Field(default=None, description="Function signature/name if shown")
    raw_hex: str = Field(examples=["0x"])


class EventLog(BaseModel):
    log_index: Optional[int] = None
    contract_address: str
    topics: list[str] = Field(default_factory=list)
    data: str = "0x"


class TransactionDetail(BaseModel):
    hash: str
    status: str = Field(examples=["success", "failed"])
    block: int
    timestamp: Optional[str] = Field(default=None, description="ISO 8601 UTC")
    from_address: str
    to_address: Optional[str] = Field(default=None, description="None for contract creation")
    contract_created: Optional[str] = None
    value: Amount
    transaction_fee: Amount
    gas_price: Amount
    gas_limit: int
    gas_used: int
    gas_used_pct: Optional[str] = None
    nonce: Optional[int] = None
    method: Optional[str] = None
    token_transfers: list[TxTokenTransfer] = Field(default_factory=list)
    input: InputData


class TransactionLogs(BaseModel):
    data: list[EventLog] = Field(default_factory=list)
