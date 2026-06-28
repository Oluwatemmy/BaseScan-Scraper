# tests/api/test_security.py
from fastapi.testclient import TestClient

from basescan_scraper.app import create_app


def test_security_headers_present():
    client = TestClient(create_app())
    r = client.get("/health")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("Referrer-Policy") == "no-referrer"


def test_cors_enabled_when_origins_configured(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://main-project.example")
    from basescan_scraper.config import get_settings
    get_settings.cache_clear()
    client = TestClient(create_app())
    r = client.get("/health", headers={"Origin": "https://main-project.example"})
    assert r.headers.get("access-control-allow-origin") == "https://main-project.example"
    get_settings.cache_clear()  # reset for other tests


def test_no_cors_header_when_not_configured():
    from basescan_scraper.config import get_settings
    get_settings.cache_clear()
    client = TestClient(create_app())
    r = client.get("/health", headers={"Origin": "https://random.example"})
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers.keys()}
