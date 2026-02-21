"""
Tests for the intent classifier service.
Requires LLM API key configured in .env (GROQ_API_KEY).
"""

import asyncio
import pytest
from app.services.intent_classifier import classify_intent


def _run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("query", [
    "What's the latest news on Apple stock?",
    "Tell me what happened with Tesla yesterday",
])
def test_news_intent(query):
    result = _run(classify_intent(query))
    assert result.get("needs_news") is True


@pytest.mark.parametrize("query", [
    "What is AAPL's current price?",
    "Show me Google's PE ratio",
])
def test_metrics_intent(query):
    result = _run(classify_intent(query))
    assert result.get("needs_metrics") is True


@pytest.mark.parametrize("query", [
    "Should I buy Tesla stock?",
    "Is Microsoft a good investment?",
])
def test_analysis_intent(query):
    result = _run(classify_intent(query))
    assert result.get("needs_analysis") is True


@pytest.mark.parametrize("query", [
    "Compare Apple vs Microsoft",
    "Which is better: TSLA or GM?",
])
def test_comparison_intent(query):
    result = _run(classify_intent(query))
    assert result.get("needs_comparison") is True


def test_classify_returns_dict():
    result = _run(classify_intent("Tell me about AAPL"))
    assert isinstance(result, dict)
    expected_keys = {"needs_news", "needs_metrics", "needs_analysis", "needs_comparison"}
    assert expected_keys.issubset(result.keys())
