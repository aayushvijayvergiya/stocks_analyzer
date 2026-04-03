"""Unit tests for RecommendationsService."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from crewai import Process
from app.services.recommendations_service import RecommendationsService
from app.crew.output_models import (
    SectorRankingOutput, SectorInfo,
    SectorStocksOutput, StockPickOutput,
    SectorFundsOutput, FundPickOutput,
)
from app.utils.exceptions import CrewExecutionError


@pytest.fixture
def mock_job_store():
    return AsyncMock()


@pytest.fixture
def service(mock_job_store):
    return RecommendationsService(job_store=mock_job_store)


def make_sector_result(sectors=None):
    mock = MagicMock()
    mock.pydantic = SectorRankingOutput(sectors=sectors or [
        SectorInfo(name="Technology", performance_pct=12.5, trend="Uptrend", momentum="Accelerating", drivers="AI"),
        SectorInfo(name="Healthcare", performance_pct=8.3, trend="Uptrend", momentum="Neutral", drivers="Aging"),
        SectorInfo(name="Financials", performance_pct=6.7, trend="Uptrend", momentum="Decelerating", drivers="Rates"),
    ])
    return mock


def make_stocks_result(sector="Technology", market="US"):
    mock = MagicMock()
    mock.pydantic = SectorStocksOutput(
        sector=sector, market=market,
        stocks=[StockPickOutput(
            symbol="AAPL", company_name="Apple Inc.",
            current_price=175.0, currency="USD",
            change_percent=5.0, recommendation_score=9.0,
            reasoning="Strong fundamentals."
        )]
    )
    return mock


def make_funds_result(sector="Technology", market="US"):
    mock = MagicMock()
    mock.pydantic = SectorFundsOutput(
        sector=sector, market=market,
        funds=[FundPickOutput(
            symbol="XLK", name="Technology Select Sector SPDR",
            current_nav=195.0, currency="USD",
            change_percent=3.2, recommendation_score=8.5,
            reasoning="Top tech ETF."
        )]
    )
    return mock


# ---------------------------------------------------------------------------
# Existing tests — rewritten to mock at the helper level, not _run_crew_with_timeout,
# so they are safe under parallel execution (no assumed call order).
# ---------------------------------------------------------------------------

async def test_stock_recommendations_returns_completed_status(service):
    """execute_stock_recommendations must return status='completed' on success."""
    with patch.object(service, "_run_market_stock_analysis", return_value=[
        {"sector": "Technology", "rank": 1, "performance_percent": 12.5,
         "market": "US", "top_stocks": [{"symbol": "AAPL"}]},
    ]):
        result = await service.execute_stock_recommendations(market="US", timeframe="30d")

    assert result["status"] == "completed"
    assert len(result["top_sectors"]) == 1


async def test_fund_recommendations_calls_fund_analysis_not_stock(service):
    """Fund flow must call _run_market_fund_analysis, never _run_market_stock_analysis."""
    with patch.object(service, "_run_market_fund_analysis", return_value=[
        {"sector": "Technology", "rank": 1, "performance_percent": 12.5,
         "market": "US", "top_funds": [{"symbol": "XLK"}]},
    ]) as mock_fund, \
    patch.object(service, "_run_market_stock_analysis") as mock_stock:
        await service.execute_fund_recommendations(market="US", timeframe="30d")

    mock_fund.assert_called_once()
    mock_stock.assert_not_called()


async def test_all_market_combines_us_and_in(service):
    """ALL market must produce results from both US and IN."""
    us_result = [{"sector": "Technology", "rank": 1, "performance_percent": 12.5,
                  "market": "US", "top_stocks": [{"symbol": "AAPL"}]}]
    in_result = [{"sector": "Banking", "rank": 1, "performance_percent": 10.1,
                  "market": "IN", "top_stocks": [{"symbol": "HDFCBANK.NS"}]}]

    async def fake_market_analysis(mkt, timeframe, job_id):
        return us_result if mkt == "US" else in_result

    with patch.object(service, "_run_market_stock_analysis", side_effect=fake_market_analysis):
        result = await service.execute_stock_recommendations(market="ALL", timeframe="30d")

    markets = {s["market"] for s in result["top_sectors"]}
    assert "US" in markets
    assert "IN" in markets


async def test_failed_market_sets_job_failed(service, mock_job_store):
    """If all markets fail, job_store must be updated to 'failed'."""
    with patch.object(service, "_run_market_stock_analysis",
                      side_effect=CrewExecutionError("boom")):
        with pytest.raises(CrewExecutionError):
            await service.execute_stock_recommendations(
                market="US", timeframe="30d", job_id="fail-job"
            )

    failed_calls = [
        c for c in mock_job_store.update_job.call_args_list
        if len(c[0]) > 1 and c[0][1] == "failed"
    ]
    assert len(failed_calls) == 1


async def test_stock_result_contains_real_symbol_not_placeholder(service):
    """Top stocks must not contain 'STOCK1' placeholder."""
    with patch.object(service, "_run_market_stock_analysis", return_value=[
        {"sector": "Technology", "rank": 1, "performance_percent": 12.5,
         "market": "US", "top_stocks": [{"symbol": "AAPL"}]},
    ]):
        result = await service.execute_stock_recommendations(market="US", timeframe="30d")

    all_symbols = [
        stock["symbol"]
        for sector in result["top_sectors"]
        for stock in sector["top_stocks"]
    ]
    assert "STOCK1" not in all_symbols
    assert all(len(sym) > 0 for sym in all_symbols)


# ---------------------------------------------------------------------------
# New tests — parallel execution, partial failure, crew config, reflection
# ---------------------------------------------------------------------------

async def test_stock_sectors_run_in_parallel(service):
    """asyncio.gather is used so market analyses run concurrently."""
    gather_was_called = []
    sector_data = [{"sector": "Technology", "rank": 1, "performance_percent": 12.5,
                    "market": "US", "top_stocks": [{"symbol": "AAPL"}]}]

    async def tracking_gather(*args, **kwargs):
        gather_was_called.append(len(args))
        return [await coro for coro in args]

    with patch("app.services.recommendations_service.asyncio.gather", tracking_gather), \
         patch.object(service, "_run_market_stock_analysis", new=AsyncMock(return_value=sector_data)):
        await service.execute_stock_recommendations("US", "30d")

    assert len(gather_was_called) >= 1


async def test_partial_sector_failure_excluded(service):
    """If one sector fails, the other successful sectors are still returned."""
    mock_crew_result = MagicMock()
    mock_crew_result.pydantic = SectorRankingOutput(sectors=[
        SectorInfo(name="Technology", performance_pct=12.5, trend="Up", momentum="High", drivers="AI"),
        SectorInfo(name="Healthcare", performance_pct=8.0, trend="Up", momentum="Low", drivers="Aging"),
        SectorInfo(name="Energy", performance_pct=6.0, trend="Up", momentum="Low", drivers="Oil"),
    ])

    call_count = 0

    async def sector_side_effect(sector_info, market, timeframe, rank):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise CrewExecutionError("sector 2 failed")
        return {"sector": sector_info.name, "rank": rank,
                "performance_percent": sector_info.performance_pct,
                "market": market, "top_stocks": []}

    with patch.object(service, "_run_stock_crew_for_sector", side_effect=sector_side_effect), \
         patch.object(service, "_run_crew_with_timeout", return_value=mock_crew_result), \
         patch("app.services.recommendations_service.FinancialAgents.sector_performance_analyst",
               return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.identify_top_sectors",
               return_value=MagicMock()), \
         patch("app.services.recommendations_service.Crew"):
        result = await service._run_market_stock_analysis("US", "30d", None)

    assert len(result) == 2


async def test_all_sectors_fail_raises_error(service):
    """If all sectors fail, CrewExecutionError is raised."""
    mock_crew_result = MagicMock()
    mock_crew_result.pydantic = SectorRankingOutput(sectors=[
        SectorInfo(name="Technology", performance_pct=12.5, trend="Up", momentum="High", drivers="AI"),
        SectorInfo(name="Healthcare", performance_pct=8.0, trend="Up", momentum="Low", drivers="Aging"),
        SectorInfo(name="Energy", performance_pct=6.0, trend="Up", momentum="Low", drivers="Oil"),
    ])

    with patch.object(service, "_run_stock_crew_for_sector",
                      side_effect=CrewExecutionError("failed")), \
         patch.object(service, "_run_crew_with_timeout", return_value=mock_crew_result), \
         patch("app.services.recommendations_service.FinancialAgents.sector_performance_analyst",
               return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.identify_top_sectors",
               return_value=MagicMock()), \
         patch("app.services.recommendations_service.Crew"):
        with pytest.raises(CrewExecutionError):
            await service._run_market_stock_analysis("US", "30d", None)


async def test_sequential_crew_with_reflection_task(service):
    """Stock picking crew must use Process.sequential with both picking and reflect tasks."""
    captured_crew_kwargs = {}

    class CapturingCrew:
        def __init__(self, **kwargs):
            captured_crew_kwargs.update(kwargs)

        def kickoff(self):
            mock = MagicMock()
            mock.pydantic = make_stocks_result().pydantic
            return mock

    sector_info = SectorInfo(
        name="Technology", performance_pct=12.5,
        trend="Up", momentum="High", drivers="AI"
    )

    with patch("app.services.recommendations_service.Crew", CapturingCrew), \
         patch("app.services.recommendations_service.FinancialAgents.financial_data_analyst",
               return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.investment_advisor",
               return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.find_top_stocks_in_sector",
               return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.reflect_on_stock_picks",
               return_value=MagicMock()):
        await service._run_stock_crew_for_sector(sector_info, "US", "30d", rank=1)

    assert captured_crew_kwargs.get("process") == Process.sequential
    assert captured_crew_kwargs.get("memory") is False
    assert len(captured_crew_kwargs.get("tasks", [])) == 2
