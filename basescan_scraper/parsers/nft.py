import json

from selectolax.parser import HTMLParser

from basescan_scraper.models.address import NftTransfer
from basescan_scraper.parsers.common import ParseError, clean_text, to_iso_utc


def _method_text(html_badge: str | None) -> str | None:
    if not html_badge:
        return None
    txt = clean_text(HTMLParser(html_badge).text(deep=True))
    return txt or None


def _collection(nft_name: str | None) -> str | None:
    if not nft_name:
        return None
    name = clean_text(nft_name)
    return name[len("NFT:"):].strip() if name.upper().startswith("NFT:") else name


def parse_nft_transfers(json_text: str) -> tuple[list[NftTransfer], int | None]:
    """Parse the GetTableData_NftTransfers response. Returns (rows, records_total)."""
    try:
        payload = json.loads(json_text)
        inner = payload["d"]
        if isinstance(inner, str):
            inner = json.loads(inner)
        records = inner["data"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ParseError(f"unexpected NFT response shape: {exc}") from exc

    total = inner.get("recordsTotal")
    rows: list[NftTransfer] = []
    for r in records:
        rows.append(
            NftTransfer(
                hash=r["txhash"],
                block=int(r["blockNumber"]),
                timestamp=to_iso_utc(r.get("dt")),
                from_address=(r.get("_from") or "").lower(),
                to_address=(r.get("_to") or "").lower(),
                token_type=f"ERC-{r.get('type')}" if r.get("type") else "",
                token_id=r.get("tokenId") or None,
                token_address=(r.get("tokenAddress") or "").lower() or None,
                collection_name=_collection(r.get("nftName")),
                quantity=r.get("value") or None,
                method=_method_text(r.get("txMethod")),
            )
        )
    return rows, total
