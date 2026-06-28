# tests/unit/test_config.py
from basescan_scraper.config import Settings


def test_defaults_are_sane():
    s = Settings(_env_file=None)
    assert s.base_url.startswith("https://")
    assert s.request_timeout_seconds > 0
    assert s.max_response_bytes >= 1_000_000
    assert s.cache_ttl_seconds >= 0
    assert s.max_page_offset >= 1


def test_env_override(monkeypatch):
    monkeypatch.setenv("CACHE_TTL_SECONDS", "99")
    s = Settings(_env_file=None)
    assert s.cache_ttl_seconds == 99


def test_allowed_origins_parses_csv(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.com,https://b.com")
    s = Settings(_env_file=None)
    assert s.allowed_origins == ["https://a.com", "https://b.com"]
