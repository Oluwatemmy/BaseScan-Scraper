# tests/api/test_validation.py
import pytest

from basescan_scraper.api.validators import normalize_address, ValidationError


def test_valid_address_normalized_lowercase():
    a = normalize_address("0x71C7656EC7ab88b098defB751B7401B5f6d8976F")
    assert a == "0x71c7656ec7ab88b098defb751b7401b5f6d8976f"


@pytest.mark.parametrize("bad", ["0x123", "71c7656e", "0xZZZ", "../etc/passwd", ""])
def test_invalid_address_rejected(bad):
    with pytest.raises(ValidationError):
        normalize_address(bad)


@pytest.mark.parametrize("bad", [
    "0x71c7656ec7ab88b098defb751b7401b5f6d8976f0",   # 41 hex (too long)
    "0x71c7656ec7ab88b098defb751b7401b5f6d8976",      # 39 hex (too short)
    "0x71c7656ec7ab88b098defb751b7401b5f6d8976g",      # non-hex char
    "0X71c7656ec7ab88b098defb751b7401b5f6d8976f",      # uppercase 0X prefix
    "0x71c7656e/../../address/0xabc",                   # path traversal attempt
    "0x71c7656ec7ab88b098defb751b7401b5f6d8976f\n",    # trailing newline
])
def test_address_rejects_adversarial(bad):
    with pytest.raises(ValidationError):
        normalize_address(bad)
