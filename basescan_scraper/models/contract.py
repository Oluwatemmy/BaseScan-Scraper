from typing import Optional

from pydantic import BaseModel, Field


class SourceFile(BaseModel):
    filename: str = Field(examples=["WETH9"])
    content: str


class ContractInfo(BaseModel):
    address: str
    is_contract: bool
    is_verified: bool
    contract_name: Optional[str] = None
    compiler_version: Optional[str] = Field(default=None, examples=["v0.5.17+commit.d19bba13"])
    optimization_enabled: Optional[bool] = None
    optimization_runs: Optional[int] = Field(default=None, examples=[10000])
    evm_version: Optional[str] = Field(default=None, examples=["default"])
    license_type: Optional[str] = Field(default=None, examples=["MIT"])
    source_files: list[SourceFile] = Field(default_factory=list)
    abi: Optional[list] = None
    constructor_arguments: Optional[str] = None
    is_proxy: bool = False
    implementation_address: Optional[str] = None
