"""
Integration tests for POST /api/v1/chat.
Requires the server to be running: uvicorn app.main:app --reload
"""

import pytest
import httpx

BASE_URL = "http://localhost:8000"


def test_chat_us_stock():
    payload = {
        "stock_symbol": "AAPL",
        "message": "What is the current price?",
    }
    with httpx.Client(base_url=BASE_URL, timeout=60.0) as client:
        response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert data["stock_symbol"] == "AAPL"
    assert isinstance(data["response"], str)
    assert len(data["response"]) > 10


def test_chat_indian_stock():
    payload = {
        "stock_symbol": "RELIANCE",
        "message": "Give me a brief summary.",
    }
    with httpx.Client(base_url=BASE_URL, timeout=60.0) as client:
        response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert isinstance(data["response"], str)


def test_chat_invalid_symbol_returns_error():
    payload = {
        "stock_symbol": "INVALID_SYMBOL_XYZ123",
        "message": "What is the price?",
    }
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        response = client.post("/api/v1/chat", json=payload)
    assert response.status_code in (400, 404, 422)


def test_chat_missing_message_returns_422():
    payload = {"stock_symbol": "AAPL"}
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == 422


def test_chat_missing_stock_symbol_returns_400():
    """stock_symbol is required — omitting it returns 400, not 422."""
    payload = {"message": "What is the price?"}
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == 400


def test_chat_response_has_sources_list():
    payload = {"stock_symbol": "AAPL", "message": "What is the current price?"}
    with httpx.Client(base_url=BASE_URL, timeout=60.0) as client:
        response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    assert isinstance(response.json()["sources"], list)


def test_chat_response_has_agent_reasoning():
    payload = {"stock_symbol": "AAPL", "message": "What is the current price?"}
    with httpx.Client(base_url=BASE_URL, timeout=60.0) as client:
        response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["agent_reasoning"] is not None
    assert isinstance(data["agent_reasoning"], str)
