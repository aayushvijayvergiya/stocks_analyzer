"""Unit tests for ChatService."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.chat_service import ChatService
from app.crew.output_models import ChatAnswerOutput
from app.utils.exceptions import CrewExecutionError
from app.models.requests import Source


@pytest.fixture
def mock_job_store():
    store = AsyncMock()
    store.create_job = AsyncMock()
    store.update_job = AsyncMock()
    return store


@pytest.fixture
def service(mock_job_store):
    return ChatService(job_store=mock_job_store)


def make_mock_crew_result(response="AAPL is at $175", sources=None, reasoning="From yfinance"):
    mock_result = MagicMock()
    mock_result.pydantic = ChatAnswerOutput(
        response=response,
        sources=sources or [Source(title="yfinance", url="https://finance.yahoo.com", date="2026-03-29")],
        agent_reasoning=reasoning
    )
    return mock_result


async def test_news_intent_calls_research_news_task_not_metrics(service):
    """When intent is news-only, research_stock_news is called but analyze_stock_financials is not."""
    with patch("app.services.chat_service.classify_intent",
               return_value={"needs_news": True, "needs_metrics": False, "needs_analysis": False, "needs_comparison": False}), \
         patch("app.services.chat_service.FinancialTasks.research_stock_news", return_value=MagicMock()) as mock_news, \
         patch("app.services.chat_service.FinancialTasks.analyze_stock_financials", return_value=MagicMock()) as mock_metrics, \
         patch("app.services.chat_service.FinancialTasks.synthesize_chat_response", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.market_researcher", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.financial_data_analyst", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.investment_advisor", return_value=MagicMock()), \
         patch("app.services.chat_service.Crew", return_value=MagicMock()), \
         patch.object(service, "_run_crew_with_timeout", return_value=make_mock_crew_result()):

        await service.execute_chat_query(
            message="What's the latest AAPL news?",
            stock_symbol="AAPL",
            market="US"
        )

    mock_news.assert_called_once()
    mock_metrics.assert_not_called()


async def test_metrics_intent_calls_financials_task_not_news(service):
    """When intent is metrics-only, analyze_stock_financials is called but research_stock_news is not."""
    with patch("app.services.chat_service.classify_intent",
               return_value={"needs_news": False, "needs_metrics": True, "needs_analysis": False, "needs_comparison": False}), \
         patch("app.services.chat_service.FinancialTasks.research_stock_news", return_value=MagicMock()) as mock_news, \
         patch("app.services.chat_service.FinancialTasks.analyze_stock_financials", return_value=MagicMock()) as mock_metrics, \
         patch("app.services.chat_service.FinancialTasks.synthesize_chat_response", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.market_researcher", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.financial_data_analyst", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.investment_advisor", return_value=MagicMock()), \
         patch("app.services.chat_service.Crew", return_value=MagicMock()), \
         patch.object(service, "_run_crew_with_timeout", return_value=make_mock_crew_result()):

        await service.execute_chat_query(
            message="What is AAPL P/E ratio?",
            stock_symbol="AAPL",
            market="US"
        )

    mock_news.assert_not_called()
    mock_metrics.assert_called_once()


async def test_no_intent_defaults_to_financials_task(service):
    """When no intent flags are set, analyze_stock_financials is called as default."""
    with patch("app.services.chat_service.classify_intent",
               return_value={"needs_news": False, "needs_metrics": False, "needs_analysis": False, "needs_comparison": False}), \
         patch("app.services.chat_service.FinancialTasks.research_stock_news", return_value=MagicMock()) as mock_news, \
         patch("app.services.chat_service.FinancialTasks.analyze_stock_financials", return_value=MagicMock()) as mock_metrics, \
         patch("app.services.chat_service.FinancialTasks.synthesize_chat_response", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.market_researcher", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.financial_data_analyst", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.investment_advisor", return_value=MagicMock()), \
         patch("app.services.chat_service.Crew", return_value=MagicMock()), \
         patch.object(service, "_run_crew_with_timeout", return_value=make_mock_crew_result()):

        await service.execute_chat_query(
            message="Tell me about AAPL",
            stock_symbol="AAPL",
            market="US"
        )

    mock_metrics.assert_called_once()
    mock_news.assert_not_called()


async def test_timeout_raises_crew_execution_error(service):
    with patch("app.services.chat_service.classify_intent",
               return_value={"needs_news": False, "needs_metrics": True, "needs_analysis": False, "needs_comparison": False}), \
         patch("app.services.chat_service.FinancialTasks.analyze_stock_financials", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialTasks.synthesize_chat_response", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.market_researcher", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.financial_data_analyst", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.investment_advisor", return_value=MagicMock()), \
         patch("app.services.chat_service.Crew", return_value=MagicMock()), \
         patch.object(service, "_run_crew_with_timeout", side_effect=asyncio.TimeoutError()):

        with pytest.raises(CrewExecutionError, match="timed out"):
            await service.execute_chat_query(
                message="AAPL price?", stock_symbol="AAPL", market="US"
            )


async def test_job_store_status_progression(service, mock_job_store):
    """Job store must be called: create → processing → completed."""
    with patch("app.services.chat_service.classify_intent",
               return_value={"needs_news": False, "needs_metrics": True, "needs_analysis": False, "needs_comparison": False}), \
         patch("app.services.chat_service.FinancialTasks.analyze_stock_financials", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialTasks.synthesize_chat_response", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.market_researcher", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.financial_data_analyst", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.investment_advisor", return_value=MagicMock()), \
         patch("app.services.chat_service.Crew", return_value=MagicMock()), \
         patch.object(service, "_run_crew_with_timeout", return_value=make_mock_crew_result()):

        await service.execute_chat_query(
            message="AAPL price?", stock_symbol="AAPL", market="US", job_id="job-xyz"
        )

    mock_job_store.create_job.assert_called_once_with("job-xyz", "chat")
    statuses = [call[0][1] for call in mock_job_store.update_job.call_args_list]
    assert statuses[0] == "processing"
    assert statuses[-1] == "completed"


async def test_result_contains_response_sources_reasoning(service):
    """Result dict must have response, sources, agent_reasoning populated."""
    crew_result = make_mock_crew_result(
        response="AAPL is at $175 with strong earnings.",
        sources=[Source(title="Reuters", url="https://reuters.com", date="2026-03-29")],
        reasoning="Fetched from yfinance and recent news."
    )
    with patch("app.services.chat_service.classify_intent",
               return_value={"needs_news": False, "needs_metrics": True, "needs_analysis": False, "needs_comparison": False}), \
         patch("app.services.chat_service.FinancialTasks.analyze_stock_financials", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialTasks.synthesize_chat_response", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.market_researcher", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.financial_data_analyst", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.investment_advisor", return_value=MagicMock()), \
         patch("app.services.chat_service.Crew", return_value=MagicMock()), \
         patch.object(service, "_run_crew_with_timeout", return_value=crew_result):

        result = await service.execute_chat_query(
            message="AAPL price?", stock_symbol="AAPL", market="US"
        )

    assert result["response"] == "AAPL is at $175 with strong earnings."
    assert len(result["sources"]) == 1
    assert result["agent_reasoning"] == "Fetched from yfinance and recent news."
