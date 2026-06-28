# basescan_scraper/api/routers/health.py
from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["Health"], summary="Liveness check")
def health() -> dict[str, str]:
    """Return service liveness. Does not scrape BaseScan."""
    return {"status": "ok"}
