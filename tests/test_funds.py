"""
Integration tests for fund/ETF recommendations endpoints.
Requires the server to be running: uvicorn app.main:app --reload
"""

import pytest
import httpx

BASE_URL = "http://localhost:8000"


def test_fund_recommendations_job_created():
    payload = {"timeframe": "1mo", "market": "US"}
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        response = client.post("/api/v1/funds/recommendations", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["status"] in ("queued", "processing", "completed")


def test_fund_recommendations_with_sector():
    payload = {"timeframe": "1mo", "market": "US", "sector": "Technology"}
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        response = client.post("/api/v1/funds/recommendations", json=payload)
    assert response.status_code == 200
    assert "job_id" in response.json()


def test_fund_recommendations_india_market():
    payload = {"timeframe": "1mo", "market": "IN"}
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        response = client.post("/api/v1/funds/recommendations", json=payload)
    assert response.status_code == 200
    assert "job_id" in response.json()


def test_fund_recommendations_invalid_job_id():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        response = client.get("/api/v1/funds/recommendations/nonexistent-job-id")
    assert response.status_code == 404
