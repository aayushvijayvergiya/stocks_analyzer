"""
Tests for CrewAI agent and crew service initialization.
Requires LLM API key configured in .env (GROQ_API_KEY).
"""

import pytest
from app.crew.agents import FinancialAgents
from app.crew.tasks import FinancialTasks
from app.services.crew_service import CrewService


def test_market_researcher_agent():
    agent = FinancialAgents.market_researcher()
    assert agent.role
    assert isinstance(agent.tools, list)


def test_financial_data_analyst_agent():
    agent = FinancialAgents.financial_data_analyst()
    assert agent.role
    assert isinstance(agent.tools, list)


def test_sector_performance_analyst_agent():
    agent = FinancialAgents.sector_performance_analyst()
    assert agent.role
    assert isinstance(agent.tools, list)


def test_investment_advisor_agent():
    agent = FinancialAgents.investment_advisor()
    assert agent.role
    assert isinstance(agent.tools, list)


def test_stock_news_task_creation():
    agent = FinancialAgents.market_researcher()
    task = FinancialTasks.research_stock_news(agent, "AAPL", "Apple Inc.")
    assert task is not None


def test_sector_identification_task_creation():
    agent = FinancialAgents.market_researcher()
    task = FinancialTasks.identify_top_sectors(agent, "US", "1mo")
    assert task is not None


def test_chat_synthesis_task_creation():
    agent = FinancialAgents.market_researcher()
    task = FinancialTasks.synthesize_chat_response(agent, "What's the price of AAPL?", "AAPL", "US")
    assert task is not None


def test_crew_service_initializes():
    service = CrewService(job_store=None)
    assert service is not None
