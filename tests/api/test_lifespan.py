# tests/api/test_lifespan.py
from fastapi.testclient import TestClient

from basescan_scraper.app import create_app


def test_lifespan_startup_and_shutdown_clean():
    # Using TestClient as a context manager triggers startup + shutdown,
    # exercising the lifespan (which closes the cached fetcher on shutdown).
    with TestClient(create_app()) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
