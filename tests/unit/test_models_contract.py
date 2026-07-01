from basescan_scraper.models.contract import ContractInfo, SourceFile


def test_source_file():
    f = SourceFile(filename="WETH9", content="pragma solidity;")
    assert f.filename == "WETH9"


def test_contract_info_minimal():
    c = ContractInfo(address="0x" + "1" * 40, is_contract=False, is_verified=False)
    assert c.is_contract is False
    assert c.source_files == []
    assert c.abi is None
    assert c.is_proxy is False
