from pathlib import Path

from basescan_scraper.parsers.contract import parse_contract

FX = Path(__file__).parent.parent / "fixtures"
WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"


def _html(name):
    return (FX / name).read_text(encoding="utf-8")


def test_weth_metadata():
    c = parse_contract(_html("contract_weth.html"), address=WETH)
    assert c.contract_name == "WETH9"
    assert c.compiler_version == "v0.5.17+commit.d19bba13"
    assert c.optimization_enabled is True
    assert c.optimization_runs == 10000
    assert c.evm_version == "default"
    assert c.license_type == "GNU LGPLv3"
    assert c.is_proxy is False
    assert c.implementation_address is None
    assert c.constructor_arguments is None


def test_usdc_proxy_and_constructor():
    c = parse_contract(_html("contract_proxy_usdc.html"), address=USDC)
    assert c.contract_name == "FiatTokenProxy"
    assert c.evm_version == "istanbul"
    assert c.license_type is None  # USDC page shows "-NA-" -> null
    assert c.is_proxy is True
    assert c.implementation_address == "0x2ce6311ddae708829bc0784c967b7d77d19fd779"
    assert c.constructor_arguments is not None
    assert c.constructor_arguments.startswith("0") or c.constructor_arguments.startswith("0x")
