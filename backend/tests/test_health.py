"""
Integration tests for /health and / endpoints.
Requires the server to be running: uvicorn app.main:app --reload
"""

import pytest
import httpx

BASE_URL = "http://localhost:8000"


def test_root():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert "docs" in data
    assert "api_v1" in data


def test_health_status_code():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        response = client.get("/health")
    assert response.status_code == 200


def test_health_response_shape():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        response = client.get("/health")
    data = response.json()
    assert "status" in data
    assert "redis_status" in data
    assert "version" in data
    assert "environment" in data


def test_health_status_values():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        response = client.get("/health")
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert data["redis_status"] in ("connected", "disconnected")


def test_api_v1_root():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        response = client.get("/api/v1/")
    assert response.status_code == 200
    data = response.json()
    assert "endpoints" in data
