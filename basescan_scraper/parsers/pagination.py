import re

_TOTAL_RE = re.compile(r"A total of ([\d,]+)")
_PAGES_RE = re.compile(r"Page \d+ of ([\d,]+)")


def parse_pagination(html: str) -> tuple[int | None, int]:
    """Return (total_items, total_pages) from a BaseScan list page.

    total_items is None if the 'A total of N' marker is absent; total_pages
    defaults to 1 if the 'Page X of Y' marker is absent.
    """
    tot_m = _TOTAL_RE.search(html)
    total = int(tot_m.group(1).replace(",", "")) if tot_m else None
    pg_m = _PAGES_RE.search(html)
    pages = int(pg_m.group(1).replace(",", "")) if pg_m else 1
    return total, pages
