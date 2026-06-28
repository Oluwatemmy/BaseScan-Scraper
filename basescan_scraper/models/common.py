# basescan_scraper/models/common.py
from decimal import Decimal
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Amount(BaseModel):
    """A token/ETH amount. `wei` is the exact integer as a string; `decimal` is
    human-readable. Strings are used so large integers never lose precision."""

    wei: str = Field(examples=["309061258262416160"])
    decimal: str = Field(examples=["0.30906125826241616"])
    symbol: Optional[str] = Field(default=None, examples=["ETH"])

    @classmethod
    def from_wei(cls, wei: str | int, decimals: int = 18, symbol: str | None = None) -> "Amount":
        wei_int = int(str(wei))  # raises ValueError on bad input
        dec = Decimal(wei_int) / (Decimal(10) ** decimals)
        # normalize: no scientific notation, strip trailing zeros
        dec_str = format(dec.normalize(), "f")
        return cls(wei=str(wei_int), decimal=dec_str, symbol=symbol)


class Pagination(BaseModel):
    page: int = Field(examples=[1], ge=1)
    offset: int = Field(examples=[25], ge=1, description="Items per page")
    total: Optional[int] = Field(default=None, examples=[96], description="Total items if known")
    has_next: bool = Field(examples=[True])


class Page(BaseModel, Generic[T]):
    data: list[T]
    pagination: Pagination


class ProblemDetail(BaseModel):
    """RFC 9457 Problem Details for HTTP APIs."""

    type: str = Field(examples=["/errors/not-found"])
    title: str = Field(examples=["Address not found"])
    status: int = Field(examples=[404])
    detail: Optional[str] = Field(default=None, examples=["No data for 0x… on Base."])
