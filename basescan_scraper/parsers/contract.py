import json
import re

from selectolax.parser import HTMLParser

from basescan_scraper.models.contract import ContractInfo, SourceFile
from basescan_scraper.parsers.common import clean_text

_CTOR_RE = re.compile(r"Constructor Arguments[\s\S]{0,400}?([0-9a-fA-F]{64,})")


def is_contract_page(html: str) -> bool:
    """True when the address is a contract (has the contract tab), not an EOA."""
    return HTMLParser(html).css_first("#ContentPlaceHolder1_li_contracts") is not None


def _source_files(tree: HTMLParser) -> list[SourceFile]:
    files: list[SourceFile] = []
    for inp in tree.css("input[name='chkContractFile']"):
        name = inp.attributes.get("data-cname")
        src = inp.attributes.get("data-csource")
        if name is not None and src is not None:
            files.append(SourceFile(filename=name, content=src))
    return files


def _abi(tree: HTMLParser) -> list | None:
    node = tree.css_first("pre#js-copytextarea2")
    if node is None:
        return None
    text = node.text(deep=True).strip()
    if not text:
        return None
    # Degrade to null (not a 502) when the ABI blob isn't valid JSON — an
    # unverified/drifted page may render a message here, and deeply-nested JSON
    # from a hostile upstream raises RecursionError (not a JSONDecodeError). The
    # ABI is one field among many; a bad ABI shouldn't fail the whole response.
    try:
        parsed = json.loads(text)
    except (ValueError, RecursionError):
        return None
    return parsed if isinstance(parsed, list) else None


def _meta_value(tree: HTMLParser, label: str) -> str | None:
    """Find the <h6> whose text == label, return the next element sibling's text."""
    for h6 in tree.css("h6"):
        if clean_text(h6.text(deep=True)) == label:
            sib = h6.next
            while sib is not None and (sib.tag == "-text" or not clean_text(sib.text(deep=True))):
                sib = sib.next
            return clean_text(sib.text(deep=True)) if sib is not None else None
    return None


def _implementation_address(html: str) -> str | None:
    # Anchor on the attribute-close+tag-open (`ImplementationAddress'>` /
    # `ImplementationAddress">`) so we hit the real element, not the earlier
    # CSS rule `#divImplementationAddress {` in a <style> block.
    m = re.search(
        r"ImplementationAddress['\"]>[\s\S]{0,300}?/address/(0x[0-9a-fA-F]{40})", html)
    return m.group(1).lower() if m else None


def _constructor_args(html: str) -> str | None:
    m = _CTOR_RE.search(html)
    return m.group(1) if m else None


def parse_contract(html: str, address: str) -> ContractInfo:
    tree = HTMLParser(html)
    is_contract = tree.css_first("#ContentPlaceHolder1_li_contracts") is not None
    source_files = _source_files(tree)
    abi = _abi(tree)
    is_verified = bool(source_files) or abi is not None

    contract_name = _meta_value(tree, "Contract Name")
    compiler_version = _meta_value(tree, "Compiler Version")

    opt = _meta_value(tree, "Optimization Enabled")
    optimization_enabled = opt.startswith("Yes") if opt else None
    if opt and "runs" in opt:
        m = re.search(r"(\d[\d,]*)\s*runs", opt)
        optimization_runs = int(m.group(1).replace(",", "")) if m else None
    else:
        optimization_runs = None

    other = _meta_value(tree, "Other Settings")
    evm_version = other.split()[0] if other else None

    # The metadata box is labelled "License" (BaseScan shows "-NA-" when none).
    license_type = _meta_value(tree, "License") or _meta_value(tree, "License Type")
    if license_type in ("-NA-", "", "None"):
        license_type = None

    return ContractInfo(
        address=address.lower(),
        is_contract=is_contract,
        is_verified=is_verified,
        contract_name=contract_name,
        compiler_version=compiler_version,
        optimization_enabled=optimization_enabled,
        optimization_runs=optimization_runs,
        evm_version=evm_version,
        license_type=license_type,
        source_files=source_files,
        abi=abi,
        constructor_arguments=_constructor_args(html),
        is_proxy="Read as Proxy" in html,
        implementation_address=_implementation_address(html),
    )
