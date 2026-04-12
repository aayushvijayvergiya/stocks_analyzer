"""Tests for agent factory and task factory (prefetch architecture)."""

from app.crew.agents import FinancialAgents
from app.crew.tasks import FinancialTasks


def test_financial_data_analyst_has_no_tools_and_low_iter():
    """Prefetch architecture: data analyst must NOT call tools."""
    agent = FinancialAgents.financial_data_analyst()
    assert agent.tools == []
    assert agent.max_iter == 2


def test_investment_advisor_has_no_tools_and_low_iter():
    """Prefetch architecture: advisor must NOT call tools."""
    agent = FinancialAgents.investment_advisor()
    assert agent.tools == []
    assert agent.max_iter == 2


def test_find_top_stocks_task_embeds_prefetched_data():
    agent = FinancialAgents.financial_data_analyst()
    prefetched = [{
        "symbol": "AAPL", "name": "Apple Inc.", "price": 175.5,
        "currency": "USD", "change_pct": 5.2, "pe_ratio": 28.5,
        "eps": 6.13, "roe": 35.0, "market_cap": 2.8e12, "debt_to_equity": 1.8,
    }]
    task = FinancialTasks.find_top_stocks_in_sector(
        agent, "Technology", "US", "30d", prefetched
    )
    desc = task.description
    assert "PREFETCHED STOCK DATA" in desc
    assert "AAPL" in desc
    assert "175.5" in desc
    # Must not instruct tool use
    assert "Multi-Stock Data Fetcher" not in desc
    assert "Sector Stocks Finder" not in desc


def test_identify_top_etfs_task_embeds_prefetched_data():
    agent = FinancialAgents.financial_data_analyst()
    prefetched = [{
        "symbol": "XLK", "name": "Tech SPDR", "price": 195.0,
        "currency": "USD", "change_pct": 3.2,
    }]
    task = FinancialTasks.identify_top_etfs_in_sector(
        agent, "Technology", "US", "30d", prefetched
    )
    desc = task.description
    assert "PREFETCHED FUND DATA" in desc
    assert "XLK" in desc


def test_synthesize_chat_response_embeds_prefetched_context():
    agent = FinancialAgents.investment_advisor()
    snapshot = {"symbol": "MSFT", "price": 410.0, "pe_ratio": 35.0}
    news = [{"title": "Earnings beat", "publisher": "Reuters",
             "link": "http://x", "date": "2026-04-10"}]
    task = FinancialTasks.synthesize_chat_response(
        agent, "How is MSFT doing?", "MSFT", "US", snapshot, news
    )
    desc = task.description
    assert "PREFETCHED STOCK SNAPSHOT" in desc
    assert "PREFETCHED NEWS" in desc
    assert "MSFT" in desc
    assert "Earnings beat" in desc


def test_crew_timeout_default_fits_prefetch_budget():
    """With prefetched data and max_iter=2, each crew should complete in 15–30s."""
    from app.config import settings
    assert 60 <= settings.CREW_TIMEOUT_SECONDS <= 90
