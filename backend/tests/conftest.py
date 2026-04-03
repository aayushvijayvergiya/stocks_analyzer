"""Shared pytest fixtures for integration tests."""

import pytest
import httpx

BASE_URL = "http://localhost:8000"


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture(scope="session")
def http_client():
    """Synchronous HTTP client for the running server."""
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="session")
def async_http_client():
    """Async HTTP client for the running server (use with pytest-asyncio)."""
    return httpx.AsyncClient(base_url=BASE_URL, timeout=120.0)
