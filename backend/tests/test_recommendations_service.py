import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from app.services.recommendations_service import RecommendationsService
from app.crew.output_models import (
    SectorRankingOutput, SectorInfo, SectorStocksOutput, 
    StockPickOutput, SectorFundsOutput, FundPickOutput
)
from app.utils.exceptions import CrewExecutionError

@pytest.fixture
def service():
    return RecommendationsService(job_store=None)

@pytest.mark.asyncio
async def test_get_top_sectors_direct_returns_ranking(service):
    """Test the direct yfinance sector fetch path."""
    with patch.object(service, '_fetch_sectors_sync') as mock_fetch:
        mock_fetch.return_value = SectorRankingOutput(sectors=[
            SectorInfo(name="Technology", performance_pct=5.0, trend="Up", momentum="High", drivers="AI")
        ])
        
        result = await service._get_top_sectors_direct("US", "30d")
        
        assert isinstance(result, SectorRankingOutput)
        assert len(result.sectors) == 1
        assert result.sectors[0].name == "Technology"
        mock_fetch.assert_called_once_with("US", "30d")

@pytest.mark.asyncio
async def test_execute_stock_recommendations_success(service):
    """End-to-end test of stock recommendation flow with mocks."""
    ranking = SectorRankingOutput(sectors=[
        SectorInfo(name="Technology", performance_pct=5.0, trend="Up", momentum="High", drivers="AI")
    ])
    
    sector_result = {
        "sector": "Technology",
        "rank": 1,
        "performance_percent": 5.0,
        "region": "US",
        "top_stocks": []
    }
    
    with patch.object(service, '_get_top_sectors_direct', new=AsyncMock(return_value=ranking)), \
         patch.object(service, '_run_stock_crew_for_sector', new=AsyncMock(return_value=sector_result)):
        
        result = await service.execute_stock_recommendations("US", "30d")
        
        assert result["status"] == "completed"
        assert len(result["top_sectors"]) == 1
        assert result["top_sectors"][0]["sector"] == "Technology"

@pytest.mark.asyncio
async def test_execute_fund_recommendations_success(service):
    """End-to-end test of fund recommendation flow with mocks."""
    ranking = SectorRankingOutput(sectors=[
        SectorInfo(name="Technology", performance_pct=5.0, trend="Up", momentum="High", drivers="AI")
    ])
    
    sector_result = {
        "sector": "Technology",
        "rank": 1,
        "performance_percent": 5.0,
        "market": "US",
        "top_funds": []
    }
    
    with patch.object(service, '_get_top_sectors_direct', new=AsyncMock(return_value=ranking)), \
         patch.object(service, '_run_market_fund_analysis', new=AsyncMock(return_value=[sector_result])):
        
        result = await service.execute_fund_recommendations("US", "30d")
        
        assert result["status"] == "completed"
        assert len(result["top_sectors"]) == 1
        assert result["top_sectors"][0]["sector"] == "Technology"

# ---------------------------------------------------------------------------
# Prefetch architecture tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_stock_crew_for_sector_uses_prefetch_and_runner(service):
    """_run_stock_crew_for_sector must call fetch_sector_stocks_sync then run_with_cancellation."""
    sector_info = SectorInfo(
        name="Technology", performance_pct=12.5,
        trend="Up", momentum="High", drivers="AI"
    )
    prefetched = [{"symbol": "AAPL", "name": "Apple", "price": 175.0}]

    valid_output_json = SectorStocksOutput(
        sector="Technology", market="US",
        stocks=[StockPickOutput(
            symbol="AAPL", company_name="Apple Inc.",
            current_price=175.0, currency="USD",
            change_percent=5.0, recommendation_score=9.0,
            reasoning="Strong."
        )]
    ).model_dump_json()

    with patch("app.services.data_fetchers.fetch_sector_stocks_sync",
               return_value=prefetched) as mock_fetch, \
         patch("app.services.crew_runner.run_with_cancellation",
               new=AsyncMock(return_value=valid_output_json)) as mock_runner:
        result = await service._run_stock_crew_for_sector(
            sector_info, "US", "30d", rank=1
        )

    mock_fetch.assert_called_once_with("Technology", "US", "30d")
    mock_runner.assert_called_once()
    kwargs = mock_runner.call_args.kwargs
    assert kwargs["target_name"] == "stock_crew"
    assert kwargs["args"]["prefetched_stocks"] == prefetched
    assert result["sector"] == "Technology"
    assert result["top_stocks"][0]["symbol"] == "AAPL"

@pytest.mark.asyncio
async def test_run_stock_crew_raises_when_prefetch_empty(service):
    """Empty prefetched data must raise CrewExecutionError — never call the runner."""
    sector_info = SectorInfo(
        name="NotReal", performance_pct=0.0,
        trend="Up", momentum="Low", drivers=""
    )
    with patch("app.services.data_fetchers.fetch_sector_stocks_sync",
               return_value=[]), \
         patch("app.services.crew_runner.run_with_cancellation",
               new=AsyncMock()) as mock_runner:
        with pytest.raises(CrewExecutionError, match="No prefetched stock data"):
            await service._run_stock_crew_for_sector(sector_info, "US", "30d", rank=1)
    mock_runner.assert_not_called()

@pytest.mark.asyncio
async def test_run_fund_crew_for_sector_uses_prefetch_and_runner(service):
    sector_info = SectorInfo(
        name="Technology", performance_pct=12.5,
        trend="Up", momentum="High", drivers="AI"
    )
    prefetched = [{"symbol": "XLK", "name": "Tech SPDR", "price": 195.0}]

    valid_output_json = SectorFundsOutput(
        sector="Technology", market="US",
        funds=[FundPickOutput(
            symbol="XLK", name="Tech SPDR",
            current_nav=195.0, currency="USD",
            change_percent=3.2, recommendation_score=8.5,
            reasoning="Top ETF."
        )]
    ).model_dump_json()

    with patch("app.services.data_fetchers.fetch_sector_etfs_sync",
               return_value=prefetched) as mock_fetch, \
         patch("app.services.crew_runner.run_with_cancellation",
               new=AsyncMock(return_value=valid_output_json)) as mock_runner:
        result = await service._run_fund_crew_for_sector(
            sector_info, "US", "30d", rank=1
        )

    mock_fetch.assert_called_once_with("Technology", "US", "30d")
    mock_runner.assert_called_once()
    assert mock_runner.call_args.kwargs["target_name"] == "fund_crew"
    assert result["top_funds"][0]["symbol"] == "XLK"
