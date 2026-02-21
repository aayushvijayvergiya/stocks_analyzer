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
    assert data["region"] == "US"


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
    assert data["region"] == "IN"


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


def test_chat_without_symbol_is_valid():
    """stock_symbol is Optional — omitting it should not return 422."""
    payload = {"message": "What is the price?"}
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        response = client.post("/api/v1/chat", json=payload)
    assert response.status_code != 422
