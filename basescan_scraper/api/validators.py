# basescan_scraper/api/validators.py
import re

ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}\Z")
TXHASH_RE = re.compile(r"^0x[0-9a-fA-F]{64}\Z")

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 50
MAX_PAGE = 100_000


class ValidationError(ValueError):
    """Raised when a path parameter fails strict validation."""


def normalize_address(value: str) -> str:
    if not ADDRESS_RE.match(value or ""):
        raise ValidationError("Invalid address: expected 0x followed by 40 hex chars.")
    return value.lower()


def validate_txhash(value: str) -> str:
    if not TXHASH_RE.match(value or ""):
        raise ValidationError("Invalid transaction hash: expected 0x followed by 64 hex chars.")
    return value.lower()


def validate_page(value: int | None) -> int:
    page = 1 if value is None else int(value)
    if page < 1 or page > MAX_PAGE:
        raise ValidationError(f"Invalid page: must be 1..{MAX_PAGE}.")
    return page


def validate_page_size(value: int | None) -> int:
    size = DEFAULT_PAGE_SIZE if value is None else int(value)
    if size < 1 or size > MAX_PAGE_SIZE:
        raise ValidationError(f"Invalid page_size: must be 1..{MAX_PAGE_SIZE}.")
    return size
