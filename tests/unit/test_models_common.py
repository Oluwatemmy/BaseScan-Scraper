# tests/unit/test_models_common.py
from basescan_scraper.models.common import Amount, Page, Pagination, ProblemDetail


def test_amount_from_wei_keeps_precision():
    amt = Amount.from_wei("309061258262416160", decimals=18)
    assert amt.wei == "309061258262416160"          # exact string, no float
    assert amt.decimal == "0.30906125826241616"     # human readable
    assert amt.symbol is None


def test_amount_rejects_non_numeric_wei():
    import pytest
    with pytest.raises(ValueError):
        Amount.from_wei("not-a-number", decimals=18)


def test_page_envelope_shape():
    page = Page[int](data=[1, 2], pagination=Pagination(page=1, offset=25, total=2, has_next=False))
    dumped = page.model_dump()
    assert dumped["data"] == [1, 2]
    assert dumped["pagination"]["has_next"] is False


def test_problem_detail_defaults_status():
    pd = ProblemDetail(type="/errors/not-found", title="Not found", status=404)
    assert pd.status == 404
    assert pd.detail is None
