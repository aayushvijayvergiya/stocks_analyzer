"""
Intent Classifier for Financial Queries.

Uses OpenRouter for fast intent classification with JSON outputs.
"""

import json
from typing import Dict, Optional
from openai import AsyncOpenAI

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

_openrouter_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    """Return module-level OpenRouter client, creating it on first call."""
    global _openrouter_client
    if _openrouter_client is None:
        _openrouter_client = AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY.get_secret_value() if settings.OPENROUTER_API_KEY else None,
            base_url=settings.OPENROUTER_BASE_URL,
        )
    return _openrouter_client


async def classify_intent(message: str) -> Dict[str, bool]:
    """Classify user intent using OpenRouter LLM.

    Args:
        message: User's financial query

    Returns:
        Dict with intent flags: {
            "needs_news": bool,
            "needs_metrics": bool,
            "needs_analysis": bool,
            "needs_comparison": bool
        }

    Example:
        >>> intent = await classify_intent("What's the latest AAPL news?")
        >>> print(intent)
        {"needs_news": True, "needs_metrics": False, ...}
    """
    try:
        client = _get_client()

        response = await client.chat.completions.create(
            model=settings.LLM_MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": """You are an intent classifier for financial queries. Return JSON with these keys:
{"needs_news": true/false, "needs_metrics": true/false, "needs_analysis": true/false, "needs_comparison": true/false}

Guidelines:
- needs_news: User wants recent events, news, announcements, or developments
- needs_metrics: User wants financial data like price, ratios, earnings, revenue
- needs_analysis: User wants investment advice, recommendations, or forecasts
- needs_comparison: User is comparing multiple stocks

Multiple can be true. If unclear, default needs_metrics=true."""
                },
                {
                    "role": "user",
                    "content": message
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=100
        )

        content = response.choices[0].message.content
        if content is None:
            raise ValueError("Empty response from OpenRouter")
        intent = json.loads(content)
        logger.info(f"Classified intent for '{message[:50]}': {intent}")

        return {
            "needs_news": intent.get("needs_news", False),
            "needs_metrics": intent.get("needs_metrics", False),
            "needs_analysis": intent.get("needs_analysis", False),
            "needs_comparison": intent.get("needs_comparison", False),
        }

    except Exception as e:
        logger.warning(f"OpenRouter classification failed: {e}, defaulting to metrics")
        return {
            "needs_news": False,
            "needs_metrics": True,
            "needs_analysis": False,
            "needs_comparison": False,
        }
