# tests/conftest.py
import pytest
from fastapi.testclient import TestClient

from basescan_scraper.app import create_app


@pytest.fixture
def client():
    return TestClient(create_app())
