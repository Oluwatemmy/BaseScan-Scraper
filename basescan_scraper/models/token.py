from typing import Optional

from pydantic import BaseModel, Field


class TokenInfo(BaseModel):
    address: str
    name: Optional[str] = None
    symbol: Optional[str] = None
    type: Optional[str] = Field(default=None, examples=["ERC-20"])
    decimals: Optional[int] = Field(default=None, examples=[6])
    price_usd: Optional[str] = Field(default=None, examples=["0.9996"])
    max_total_supply: Optional[str] = Field(default=None, examples=["4,207,496,819.876931"])
    holders_count: Optional[int] = Field(default=None, examples=[9858749])
    market_cap_usd: Optional[str] = Field(default=None, examples=["4,205,868,518.61"])


class TokenHolder(BaseModel):
    rank: int
    address: str
    label: Optional[str] = Field(default=None, examples=["Morpho: Morpho"])
    quantity: str = Field(examples=["195,270,620.9949"])
    # BaseScan renders the percentage client-side in JS (the server HTML is a
    # "0.0000%" placeholder), so it is computed by the service as
    # quantity / total_supply * 100, and is null when supply is unknown.
    percentage: Optional[str] = Field(default=None, examples=["4.6410%"])
    value_usd: Optional[str] = Field(default=None, examples=["195,195,051.26"])
