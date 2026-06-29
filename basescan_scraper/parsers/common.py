# basescan_scraper/parsers/common.py
import re
from decimal import Decimal


class ParseError(Exception):
    """Raised when expected structure is missing (likely HTML drift)."""


def clean_text(text: str | None) -> str:
    """Collapse whitespace; return '' for None. Use on node.text(deep=True) so
    inline markup inside numbers (e.g. 0<b>.</b>309…) is already merged."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


_NUM_RE = re.compile(r"[-+]?[\d,]*\.?\d+")
_DATETIME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2}):(\d{2})$")


def to_iso_utc(text: str | None) -> str | None:
    """Convert 'YYYY-MM-DD H:MM:SS' (1- or 2-digit hour) to 'YYYY-MM-DDTHH:MM:SSZ'.
    Returns None if the text is empty or not a datetime."""
    m = _DATETIME_RE.match(clean_text(text))
    if not m:
        return None
    y, mo, d, h, mi, s = m.groups()
    return f"{y}-{mo}-{d}T{int(h):02d}:{mi}:{s}Z"


def parse_wei_from_eth_text(text: str, decimals: int = 18) -> str:
    """Extract the leading numeric value from text like '0.309… ETH' and convert
    to an exact integer wei string."""
    cleaned = clean_text(text).replace(",", "")
    m = _NUM_RE.search(cleaned)
    if not m:
        raise ValueError(f"no number in {text!r}")
    wei = (Decimal(m.group(0)) * (Decimal(10) ** decimals)).to_integral_value()
    return str(int(wei))
