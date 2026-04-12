import pytest
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone
from app.services.chat_service import ChatService
from app.crew.output_models import ChatAnswerOutput
from app.models.requests import Source

@pytest.fixture
def service():
    return ChatService(job_store=None)

@pytest.mark.asyncio
async def test_chat_service_prefetches_snapshot_and_calls_runner(service):
    """execute_chat_query must fetch snapshot, optionally news, then call runner."""
    snapshot = {"symbol": "AAPL", "price": 175.0}
    news = [{"title": "Earnings", "publisher": "Reuters",
             "link": "http://x", "date": "2026-04-10"}]
    answer = ChatAnswerOutput(
        response="AAPL is trading at $175 with strong fundamentals.",
        sources=[Source(title="Earnings", url="http://x", date="2026-04-10")],
        agent_reasoning="Read snapshot and news.",
    )

    with patch("app.services.chat_service.classify_intent",
               new=AsyncMock(return_value={"needs_news": True, "needs_metrics": True,
                                            "needs_analysis": False, "needs_comparison": False})), \
         patch("app.services.chat_service.fetch_stock_snapshot_sync",
               return_value=snapshot) as mock_snap, \
         patch("app.services.chat_service.fetch_stock_news_sync",
               return_value=news) as mock_news, \
         patch("app.services.chat_service.run_with_cancellation",
               new=AsyncMock(return_value=answer.model_dump_json())) as mock_runner:
        result = await service.execute_chat_query("How is AAPL?", "AAPL", "US")

    mock_snap.assert_called_once()
    mock_news.assert_called_once()
    mock_runner.assert_called_once()
    kwargs = mock_runner.call_args.kwargs
    assert kwargs["target_name"] == "chat_crew"
    assert kwargs["args"]["prefetched_snapshot"] == snapshot
    assert kwargs["args"]["prefetched_news"] == news
    assert "AAPL is trading" in result["response"]

@pytest.mark.asyncio
async def test_chat_service_skips_news_when_intent_says_no(service):
    answer = ChatAnswerOutput(response="ok", sources=[], agent_reasoning="no news needed")

    with patch("app.services.chat_service.classify_intent",
               new=AsyncMock(return_value={"needs_news": False, "needs_metrics": True,
                                            "needs_analysis": False, "needs_comparison": False})), \
         patch("app.services.chat_service.fetch_stock_snapshot_sync",
               return_value={"symbol": "AAPL"}), \
         patch("app.services.chat_service.fetch_stock_news_sync",
               return_value=[]) as mock_news, \
         patch("app.services.chat_service.run_with_cancellation",
               new=AsyncMock(return_value=answer.model_dump_json())):
        await service.execute_chat_query("Price of AAPL?", "AAPL", "US")

    mock_news.assert_not_called()
