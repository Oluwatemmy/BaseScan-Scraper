# tests/api/test_validation.py
import pytest

from basescan_scraper.api.validators import (
    normalize_address,
    validate_page,
    validate_page_size,
    ValidationError,
)


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


def test_validate_page_defaults_and_lower_bound():
    assert validate_page(None) == 1
    assert validate_page(3) == 3
    with pytest.raises(ValidationError):
        validate_page(0)


def test_validate_page_upper_bound():
    assert validate_page(100_000) == 100_000
    with pytest.raises(ValidationError):
        validate_page(100_001)


def test_validate_page_size_cap():
    assert validate_page_size(None) == 50
    assert validate_page_size(100) == 100
    with pytest.raises(ValidationError):
        validate_page_size(101)
    with pytest.raises(ValidationError):
        validate_page_size(0)
