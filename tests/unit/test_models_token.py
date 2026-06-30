from basescan_scraper.models.token import TokenHolder, TokenInfo


def test_token_info_minimal():
    t = TokenInfo(address="0x" + "1" * 40)
    assert t.address.startswith("0x")
    assert t.name is None and t.decimals is None


def test_token_holder():
    h = TokenHolder(rank=1, address="0x" + "2" * 40, quantity="195,270,620.9949",
                    percentage="0.0000%")
    assert h.rank == 1
    assert h.label is None
