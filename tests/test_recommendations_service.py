"""Unit tests for RecommendationsService."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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


async def test_stock_recommendations_sector_crew_runs_first(service):
    """Sector crew must run once before per-sector stock crews (1 + 3 calls total)."""
    results = [make_sector_result()] + [make_stocks_result()] * 3
    service._run_crew_with_timeout = AsyncMock(side_effect=results)

    with patch("app.services.recommendations_service.FinancialAgents.market_researcher", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.financial_data_analyst", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.sector_performance_analyst", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.investment_advisor", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.identify_top_sectors", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.find_top_stocks_in_sector", return_value=MagicMock()), \
         patch("app.services.recommendations_service.Crew", return_value=MagicMock()):

        await service.execute_stock_recommendations(market="US", timeframe="30d")

    assert service._run_crew_with_timeout.call_count == 4  # 1 sector + 3 stocks


async def test_fund_recommendations_calls_etf_task_not_stock_task(service):
    """Fund recommendations must use identify_top_etfs_in_sector, not find_top_stocks_in_sector."""
    results = [make_sector_result()] + [make_funds_result()] * 3
    service._run_crew_with_timeout = AsyncMock(side_effect=results)

    with patch("app.services.recommendations_service.FinancialAgents.sector_performance_analyst", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.financial_data_analyst", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.investment_advisor", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.identify_top_sectors", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.identify_top_etfs_in_sector", return_value=MagicMock()) as mock_etf, \
         patch("app.services.recommendations_service.FinancialTasks.find_top_stocks_in_sector", return_value=MagicMock()) as mock_stocks, \
         patch("app.services.recommendations_service.Crew", return_value=MagicMock()):

        await service.execute_fund_recommendations(market="US", timeframe="30d")

    mock_etf.assert_called()
    mock_stocks.assert_not_called()


async def test_all_market_combines_us_and_in(service):
    """ALL market should produce results from both US and IN."""
    us_sector = make_sector_result([
        SectorInfo(name="Technology", performance_pct=12.5, trend="Uptrend", momentum="Accelerating", drivers="AI"),
        SectorInfo(name="Healthcare", performance_pct=8.3, trend="Uptrend", momentum="Neutral", drivers="Aging"),
        SectorInfo(name="Financials", performance_pct=6.7, trend="Uptrend", momentum="Decelerating", drivers="Rates"),
    ])
    in_sector = make_sector_result([
        SectorInfo(name="Banking", performance_pct=10.1, trend="Uptrend", momentum="Accelerating", drivers="Credit"),
        SectorInfo(name="Technology", performance_pct=9.5, trend="Uptrend", momentum="Neutral", drivers="Digital"),
        SectorInfo(name="Pharma", performance_pct=7.8, trend="Uptrend", momentum="Neutral", drivers="Exports"),
    ])
    us_stock = make_stocks_result("Technology", "US")
    in_stock = make_stocks_result("Banking", "IN")

    results = (
        [us_sector] + [us_stock] * 3 +
        [in_sector] + [in_stock] * 3
    )
    service._run_crew_with_timeout = AsyncMock(side_effect=results)

    with patch("app.services.recommendations_service.FinancialAgents.market_researcher", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.financial_data_analyst", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.sector_performance_analyst", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.investment_advisor", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.identify_top_sectors", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.find_top_stocks_in_sector", return_value=MagicMock()), \
         patch("app.services.recommendations_service.Crew", return_value=MagicMock()):

        result = await service.execute_stock_recommendations(market="ALL", timeframe="30d")

    markets = {s["market"] for s in result["top_sectors"]}
    assert "US" in markets
    assert "IN" in markets


async def test_failed_sector_crew_sets_job_failed(service, mock_job_store):
    """If the sector crew raises, job_store must be updated to 'failed'."""
    service._run_crew_with_timeout = AsyncMock(side_effect=Exception("Sector crew blew up"))

    with patch("app.services.recommendations_service.FinancialAgents.market_researcher", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.financial_data_analyst", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.sector_performance_analyst", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.investment_advisor", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.identify_top_sectors", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.find_top_stocks_in_sector", return_value=MagicMock()), \
         patch("app.services.recommendations_service.Crew", return_value=MagicMock()):

        with pytest.raises(CrewExecutionError):
            await service.execute_stock_recommendations(market="US", timeframe="30d", job_id="fail-job")

    failed_calls = [
        c for c in mock_job_store.update_job.call_args_list
        if len(c[0]) > 1 and c[0][1] == "failed"
    ]
    assert len(failed_calls) == 1


async def test_stock_result_contains_real_symbol_not_placeholder(service):
    """Top stocks in result must not contain 'STOCK1' placeholder."""
    results = [make_sector_result()] + [make_stocks_result()] * 3
    service._run_crew_with_timeout = AsyncMock(side_effect=results)

    with patch("app.services.recommendations_service.FinancialAgents.market_researcher", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.financial_data_analyst", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.sector_performance_analyst", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.investment_advisor", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.identify_top_sectors", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.find_top_stocks_in_sector", return_value=MagicMock()), \
         patch("app.services.recommendations_service.Crew", return_value=MagicMock()):

        result = await service.execute_stock_recommendations(market="US", timeframe="30d")

    all_symbols = [
        stock["symbol"]
        for sector in result["top_sectors"]
        for stock in sector["top_stocks"]
    ]
    assert "STOCK1" not in all_symbols
    assert all(len(sym) > 0 for sym in all_symbols)
