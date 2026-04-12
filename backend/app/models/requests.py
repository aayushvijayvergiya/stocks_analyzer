from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional, List
from datetime import datetime
import re

class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="User's question"
    )
    stock_symbol: Optional[str] = Field(
        None,
        description="Stock symbol like 'AAPL' or 'RELIANCE.NS'"
    )
    market: Optional[str] = Field(
        None,
        description="Market: 'US' or 'IN' (default: auto-detect from symbol)"
    )
    context: Optional[List[dict]] = Field(
        None,
        description="Conversation history for follow-up questions"
    )
    
    @field_validator('stock_symbol')
    def validate_stock_symbol(cls, value):
        if value is None:
            return value
        symbol = str(value).strip().upper()
        if not symbol:
            raise ValueError("stock_symbol cannot be empty")
        if not re.match(r"^[A-Z][A-Z0-9.-]{0,9}$", symbol):
            raise ValueError("stock_symbol must look like AAPL or RELIANCE.NS")
        return symbol
    

class StockRecommendationParams(BaseModel):
    timeframe: Literal["7d", "30d", "90d"] = Field(
        ...,
        description="Timeframe for which to get recommendations"
    )
    market: Optional[Literal["US", "IN"]] = Field(
        None,
        description="Market: 'US' or 'IN' (default: auto-detect from symbol)"
    )
    risk_profile: Optional[Literal["conservative", "balanced", "aggressive"]] = Field(
        None,
        description="Risk profile: 'conservative', 'balanced', 'aggressive'"
    )
    

class FundRecommendationParams(BaseModel):
    timeframe: Literal["7d", "30d", "90d"] = Field(
        ...,
        description="Timeframe for which to get recommendations"
    )
    market: Optional[Literal["US", "IN"]] = Field(
        None,
        description="Market: 'US' or 'IN'"
    )
    risk_profile: Optional[Literal["conservative", "balanced", "aggressive"]] = Field(
        None,
        description="Risk profile: 'conservative', 'balanced', 'aggressive'"
    )
    fund_type: Optional[Literal["equity", "debt", "balanced"]] = Field(
        None,
        description="Type of fund: 'equity', 'debt', 'balanced'"
    )
    
    
class Source(BaseModel):
    title: str = Field(..., description="Title of the source")
    url: str = Field(..., description="URL of the source") 
    date:str = Field(..., description="Date of the source information")
    
    
class AgentReasoning(BaseModel):
    investment_advisor: Optional[str] = Field(
        None,
        description="Reasoning from the investment advisor agent"
    )