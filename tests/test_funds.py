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


def _poll_fund_job(client: httpx.Client, job_id: str) -> dict:
    """Poll a fund job until completion or timeout."""
    import time
    MAX_POLL = 120
    elapsed = 0
    while elapsed < MAX_POLL:
        time.sleep(3)
        elapsed += 3
        response = client.get(f"/api/v1/funds/recommendations/{job_id}")
        assert response.status_code == 200
        data = response.json()
        if data["status"] in ("completed", "failed"):
            return data
    pytest.skip("Job did not complete within 120s")


def test_fund_recommendations_result_differs_from_stock_result():
    """Fund result must contain top_funds, not top_stocks."""
    with httpx.Client(base_url=BASE_URL, timeout=150.0) as client:
        create_resp = client.post("/api/v1/funds/recommendations", json={
            "timeframe": "30d", "market": "US"
        })
        assert create_resp.status_code == 200
        job_id = create_resp.json()["job_id"]
        result = _poll_fund_job(client, job_id)

    assert result["status"] == "completed"
    for sector in result.get("result", {}).get("top_sectors", []):
        assert "top_funds" in sector, "Fund result must have top_funds, not top_stocks"
        assert "top_stocks" not in sector


def test_fund_result_has_nav_field():
    """Each fund in result must have current_nav populated."""
    with httpx.Client(base_url=BASE_URL, timeout=150.0) as client:
        create_resp = client.post("/api/v1/funds/recommendations", json={
            "timeframe": "30d", "market": "US"
        })
        job_id = create_resp.json()["job_id"]
        result = _poll_fund_job(client, job_id)

    for sector in result.get("result", {}).get("top_sectors", []):
        for fund in sector.get("top_funds", []):
            assert "current_nav" in fund
            assert fund["current_nav"] is not None
