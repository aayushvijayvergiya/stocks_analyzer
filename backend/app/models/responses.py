from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from app.models.requests import AgentReasoning, Source

class ChatResponse(BaseModel):
    response: str = Field(..., description="Chatbot's response to the user's message")
    sources: List[Source]
    agent_reasoning: Optional[AgentReasoning]
    stock_symbol: Optional[str] = Field(
        None,
        description="Stock symbol related to the response, if applicable"
    )
    timestamp: datetime = Field(..., description="Timestamp of the response generation")
    
    
class JobStatus(BaseModel):
    job_id: str = Field(..., description="Unique identifier for the job")
    status: str = Field(..., description="Current status of the job (e.g., 'pending', 'in_progress', 'completed', 'failed')")
    result: Optional[dict] = Field(None, description="Result of the job if completed successfully")
    error: Optional[str] = Field(None, description="Error message if the job failed")
    progress: Optional[str] = Field(None, description="High level progress update for long-running jobs")
    created_at: datetime = Field(..., description="Timestamp when the job was created")
    completed_at: Optional[datetime] = Field(None, description="Timestamp when the job was completed")
    
    
class KeyMetrics(BaseModel):
    market_cap: Optional[float] = Field(None, description="Market capitalization")
    pe_ratio: Optional[float] = Field(None, description="Price-to-Earnings ratio")
    dividend_yield: Optional[float] = Field(None, description="Dividend yield percentage")
    volume: Optional[int] = Field(None, description="Trading volume")
    eps: Optional[float] = Field(None, description="Earnings per share")
    debt_to_equity: Optional[float] = Field(None, description="Debt to Equity ratio")
    roe: Optional[float] = Field(None, description="Return on Equity percentage")
    fifty_two_week_high: Optional[float] = Field(None, description="52-week high price")
    fifty_two_week_low: Optional[float] = Field(None, description="52-week low price")
    
    
class StockRecommendation(BaseModel):
    symbol: str = Field(..., description="Stock symbol")
    company_name: Optional[str] = Field(None, description="Full name of the company")
    current_price: Optional[float] = Field(None, description="Current stock price")
    currency: Optional[str] = Field(None, description="Currency of the stock price")
    change_percent: Optional[float] = Field(None, description="Percentage change in stock price")
    recommendation_score: Optional[float] = Field(None, description="Overall recommendation score")
    reasoning: str = Field(..., description="Reasoning behind the recommendation")
    key_metrics: Optional[KeyMetrics]
    
    
class SectorRecommendation(BaseModel):
    sector: str = Field(..., description="Name of the sector")
    performance_percent: float = Field(..., description="Overall performance of the sector over a timeframe")
    rank: int = Field(..., description="Rank of the sector compared to others")
    region: str = Field(..., description="Region of the sector (e.g., 'US', 'IN')")
    top_stocks: List[StockRecommendation] = Field(
        ...,
        description="List of top stock recommendations within the sector"
    )
    
    
class StockRecommendationResponse(BaseModel):
    job_id: str = Field(..., description="Unique identifier for the recommendation job")
    status: str = Field(..., description="Current status of the recommendation job")
    generated_at: datetime = Field(..., description="Timestamp when the recommendation was generated")
    timeframe: str = Field(..., description="Timeframe for which the recommendation is relevant")
    region: Optional[str] = Field(
        None,
        description="Market for which the recommendation is relevant (e.g., 'US', 'IN')"
    )
    top_sectors: Optional[List[SectorRecommendation]] = Field(
        None,
        description="List of top sector recommendations"
    )
    analysis_summary: Optional[str] = Field(
        None,
        description="Summary of the analysis that led to the recommendation"
    )
    cache_hit: bool = Field(
        False,
        description="Indicates whether the recommendation was served from cache"
    )
    
    
class FundRecommendation(BaseModel):
    symbol: str = Field(..., description="Fund symbol")
    name: str = Field(..., description="Full name of the fund")
    current_nav: float = Field(..., description="Current Net Asset Value")
    currency: str = Field(..., description="Currency of the NAV")
    expense_ratio: Optional[float] = Field(None, description="Expense ratio percentage")
    aum: Optional[str] = Field(None, description="Assets Under Management")
    change_percent: float = Field(..., description="Percentage change in NAV")
    recommendation_score: float = Field(..., description="Overall recommendation score")
    reasoning: str = Field(..., description="Reasoning behind the recommendation")


class SectorFundRecommendation(BaseModel):
    sector: str = Field(..., description="Name of the sector")
    performance_percent: float = Field(..., description="Overall performance of the sector")
    rank: int = Field(..., description="Rank of the sector compared to others")
    market: str = Field(..., description="Market of the sector (e.g., 'US', 'IN')")
    top_funds: List[FundRecommendation] = Field(
        ...,
        description="List of top fund recommendations within the sector"
        )


class FundRecommendationResponse(BaseModel):
    job_id: str = Field(..., description="Unique identifier for the recommendation job")
    status: str = Field(..., description="Current status of the recommendation job")
    generated_at: Optional[datetime] = Field(None, description="Timestamp when the recommendation was generated")
    timeframe: str = Field(..., description="Timeframe for which the recommendation is relevant")
    market: str = Field(..., description="Market for which the recommendation is relevant (e.g., 'US', 'IN')")
    top_sectors: Optional[List[SectorFundRecommendation]] = Field(
        None,
        description="List of top sector fund recommendations"
    )
    analysis_summary: Optional[str] = Field(
        None,
        description="Summary of the analysis that led to the recommendation"
    )
    cache_hit: bool = Field(
        False,
        description="Indicates whether the recommendation was served from cache"
    )
    note: Optional[str] = Field(
        None,
        description="Additional note (e.g., 'India mutual funds coming soon. Showing sectoral indices.')"
    )


class ErrorResponse(BaseModel):
    detail: str = Field(..., description="Error details")
    error_code: Optional[str] = Field(None, description="Error code")
    timestamp: datetime = Field(..., description="Timestamp when the error occurred")
    
    
class HealthResponse(BaseModel):
    status: str = Field(..., description="Health status of the service")
    environment: str = Field(..., description="Current environment (e.g., development, production)")
    version: str = Field(..., description="Version of the service")
    redis_status: str = Field(..., description="Status of Redis connection")
    timestamp: datetime = Field(..., description="Timestamp of the health check response")