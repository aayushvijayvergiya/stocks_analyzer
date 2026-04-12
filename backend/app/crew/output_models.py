"""
Pydantic output models for CrewAI structured task outputs.

These are used as `output_pydantic` on Task definitions so agents return
validated, typed data instead of free-form text.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from app.models.requests import Source


class SectorInfo(BaseModel):
    """A single sector with performance data."""
    name: str
    performance_pct: float
    trend: str
    momentum: str
    drivers: str


class SectorRankingOutput(BaseModel):
    """Sector ranking produced by direct yfinance fetch (_fetch_sectors_sync)."""
    sectors: List[SectorInfo]


class KeyMetricsOutput(BaseModel):
    """Financial metrics for a single stock."""
    pe_ratio: Optional[float] = None
    market_cap: Optional[float] = None
    volume: Optional[int] = None
    eps: Optional[float] = None
    debt_to_equity: Optional[float] = None
    roe: Optional[float] = None


class StockPickOutput(BaseModel):
    """A single stock recommendation."""
    symbol: str
    company_name: str
    current_price: Optional[float] = None
    currency: str
    change_percent: Optional[float] = None
    recommendation_score: float = Field(ge=0, le=10)
    reasoning: str
    key_metrics: Optional[KeyMetricsOutput] = None


class SectorStocksOutput(BaseModel):
    """Output of find_top_stocks_in_sector task."""
    sector: str
    market: str
    stocks: List[StockPickOutput]


class ChatAnswerOutput(BaseModel):
    """Output of synthesize_chat_response task."""
    response: str
    sources: List[Source]
    agent_reasoning: str


class FundPickOutput(BaseModel):
    """A single ETF/fund recommendation."""
    symbol: str
    name: str
    current_nav: Optional[float] = None
    currency: str
    expense_ratio: Optional[float] = None
    aum: Optional[str] = None
    change_percent: Optional[float] = None
    recommendation_score: float = Field(ge=0, le=10)
    reasoning: str


class SectorFundsOutput(BaseModel):
    """Output of identify_top_etfs_in_sector task."""
    sector: str
    market: str
    funds: List[FundPickOutput]
