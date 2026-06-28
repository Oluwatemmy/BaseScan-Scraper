# basescan_scraper/api/validators.py
import re

ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}\Z")
TXHASH_RE = re.compile(r"^0x[0-9a-fA-F]{64}\Z")


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
