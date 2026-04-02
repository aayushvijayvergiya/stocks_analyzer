"""Unit tests for crew structured output models."""
import pytest
from pydantic import ValidationError
from app.crew.output_models import (
    SectorInfo,
    SectorRankingOutput,
    KeyMetricsOutput,
    StockPickOutput,
    SectorStocksOutput,
    ChatAnswerOutput,
    FundPickOutput,
    SectorFundsOutput,
)
from app.models.requests import Source


# ── SectorRankingOutput ──────────────────────────────────────────────────────

def test_sector_ranking_output_valid_construction():
    output = SectorRankingOutput(sectors=[
        SectorInfo(
            name="Technology", performance_pct=12.5,
            trend="Strong Uptrend", momentum="Accelerating", drivers="AI boom"
        )
    ])
    assert len(output.sectors) == 1
    assert output.sectors[0].name == "Technology"
    assert output.sectors[0].performance_pct == 12.5


def test_sector_ranking_output_empty_sectors():
    output = SectorRankingOutput(sectors=[])
    assert output.sectors == []


# ── StockPickOutput ──────────────────────────────────────────────────────────

def test_stock_pick_output_valid():
    stock = StockPickOutput(
        symbol="AAPL", company_name="Apple Inc.",
        current_price=175.0, currency="USD",
        change_percent=2.5, recommendation_score=8.5,
        reasoning="Strong fundamentals and solid earnings growth."
    )
    assert stock.symbol == "AAPL"
    assert stock.key_metrics is None


def test_stock_pick_output_score_too_high_raises():
    with pytest.raises(ValidationError):
        StockPickOutput(
            symbol="AAPL", company_name="Apple Inc.",
            current_price=175.0, currency="USD",
            change_percent=2.5, recommendation_score=11.0,
            reasoning="Great stock."
        )


def test_stock_pick_output_score_too_low_raises():
    with pytest.raises(ValidationError):
        StockPickOutput(
            symbol="AAPL", company_name="Apple Inc.",
            current_price=175.0, currency="USD",
            change_percent=2.5, recommendation_score=-1.0,
            reasoning="Bad stock."
        )


def test_stock_pick_output_with_key_metrics():
    stock = StockPickOutput(
        symbol="AAPL", company_name="Apple Inc.",
        current_price=175.0, currency="USD",
        change_percent=2.5, recommendation_score=8.5,
        reasoning="Solid.",
        key_metrics=KeyMetricsOutput(pe_ratio=28.5, roe=0.35)
    )
    assert stock.key_metrics.pe_ratio == 28.5
    assert stock.key_metrics.market_cap is None


# ── SectorStocksOutput ───────────────────────────────────────────────────────

def test_sector_stocks_output_serialization_roundtrip():
    original = SectorStocksOutput(
        sector="Technology", market="US",
        stocks=[StockPickOutput(
            symbol="AAPL", company_name="Apple Inc.",
            current_price=175.0, currency="USD",
            change_percent=2.5, recommendation_score=8.5,
            reasoning="Strong fundamentals."
        )]
    )
    as_dict = original.model_dump()
    restored = SectorStocksOutput(**as_dict)
    assert restored.stocks[0].symbol == "AAPL"
    assert restored.sector == "Technology"


# ── ChatAnswerOutput ─────────────────────────────────────────────────────────

def test_chat_answer_output_valid():
    output = ChatAnswerOutput(
        response="Apple is trading at $175",
        sources=[Source(title="Reuters", url="https://reuters.com", date="2026-03-29")],
        agent_reasoning="Based on current price data from yfinance."
    )
    assert output.response == "Apple is trading at $175"
    assert len(output.sources) == 1
    assert output.sources[0].title == "Reuters"


def test_chat_answer_output_empty_sources():
    output = ChatAnswerOutput(
        response="AAPL current price is $175.",
        sources=[],
        agent_reasoning="Fetched from yfinance."
    )
    assert output.sources == []


# ── FundPickOutput ───────────────────────────────────────────────────────────

def test_fund_pick_output_optional_fields_default_none():
    fund = FundPickOutput(
        symbol="XLK", name="Technology Select Sector SPDR",
        current_nav=195.0, currency="USD",
        change_percent=3.2, recommendation_score=8.0,
        reasoning="Top tech ETF by AUM and liquidity."
    )
    assert fund.expense_ratio is None
    assert fund.aum is None


def test_fund_pick_output_with_all_fields():
    fund = FundPickOutput(
        symbol="XLK", name="Technology Select Sector SPDR",
        current_nav=195.0, currency="USD",
        expense_ratio=0.13, aum="$50B",
        change_percent=3.2, recommendation_score=8.0,
        reasoning="Top tech ETF."
    )
    assert fund.expense_ratio == 0.13
    assert fund.aum == "$50B"


def test_fund_pick_output_score_bounds():
    with pytest.raises(ValidationError):
        FundPickOutput(
            symbol="XLK", name="Tech SPDR",
            current_nav=195.0, currency="USD",
            change_percent=3.2, recommendation_score=10.5,
            reasoning="Great."
        )


# ── SectorFundsOutput ────────────────────────────────────────────────────────

def test_sector_funds_output_serialization_roundtrip():
    original = SectorFundsOutput(
        sector="Technology", market="US",
        funds=[FundPickOutput(
            symbol="XLK", name="Technology Select Sector SPDR",
            current_nav=195.0, currency="USD",
            change_percent=3.2, recommendation_score=8.0,
            reasoning="Top tech ETF."
        )]
    )
    as_dict = original.model_dump()
    restored = SectorFundsOutput(**as_dict)
    assert restored.funds[0].symbol == "XLK"
    assert restored.market == "US"
