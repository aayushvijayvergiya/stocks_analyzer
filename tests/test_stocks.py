"""
Integration tests for stock recommendations endpoints.
Requires the server to be running: uvicorn app.main:app --reload
"""

import time
import pytest
import httpx

BASE_URL = "http://localhost:8000"
POLL_INTERVAL = 2  # seconds
MAX_POLL_SECONDS = 90


def _poll_job(client: httpx.Client, job_id: str) -> dict:
    """Poll a job until completion or timeout."""
    elapsed = 0
    while elapsed < MAX_POLL_SECONDS:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        response = client.get(f"/api/v1/stocks/recommendations/{job_id}")
        assert response.status_code == 200
        data = response.json()
        if data["status"] in ("completed", "failed"):
            return data
    pytest.fail(f"Job {job_id} did not complete within {MAX_POLL_SECONDS}s")


def test_stock_recommendations_job_created():
    payload = {"timeframe": "1mo", "market": "US"}
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        response = client.post("/api/v1/stocks/recommendations", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["status"] in ("queued", "processing", "completed")


def test_stock_recommendations_job_completes():
    payload = {"timeframe": "1mo", "market": "US"}
    with httpx.Client(base_url=BASE_URL, timeout=MAX_POLL_SECONDS + 30.0) as client:
        create_response = client.post("/api/v1/stocks/recommendations", json=payload)
        assert create_response.status_code == 200
        job_id = create_response.json()["job_id"]

        result = _poll_job(client, job_id)
        assert result["status"] == "completed"
        assert "result" in result


def test_stock_recommendations_with_sector():
    payload = {"timeframe": "1mo", "market": "US", "sector": "Technology"}
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        response = client.post("/api/v1/stocks/recommendations", json=payload)
    assert response.status_code == 200
    assert "job_id" in response.json()


def test_stock_recommendations_invalid_job_id():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        response = client.get("/api/v1/stocks/recommendations/nonexistent-job-id")
    assert response.status_code == 404
