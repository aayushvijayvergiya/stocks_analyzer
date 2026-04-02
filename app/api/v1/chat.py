"""
Chat API endpoint - Ask questions about specific stocks.
"""

from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone

from app.models.requests import ChatRequest
from app.models.responses import ChatResponse
from app.services import CacheService, CrewService, make_chat_cache_key
from app.dependencies import get_cache_service, get_crew_service, check_rate_limit
from app.config import settings
from app.utils.logger import get_logger
from app.utils.validators import validate_and_normalize_symbol

logger = get_logger(__name__)

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    cache_service: CacheService = Depends(get_cache_service),
    crew_service: CrewService = Depends(get_crew_service),
    _ = Depends(check_rate_limit)
):
    """
    Ask questions about a specific stock.
    
    This endpoint uses AI agents to:
    - Fetch latest news and sentiment
    - Analyze financial metrics and performance
    - Provide conversational, helpful answers
    
    **Rate Limit:** 100 requests per hour per IP
    
    **Response Time:** Typically 10-30 seconds
    
    **Cache:** Responses cached for 5 minutes
    
    Example queries:
    - "What's happening with Apple stock today?"
    - "Should I buy Tesla?"
    - "Compare Microsoft and Google"
    - "What's the P/E ratio of Reliance?"
    """
    try:
        # Validate and normalize stock symbol
        stock_symbol = request.stock_symbol
        market = request.market

        if not stock_symbol:
            raise HTTPException(
                status_code=400,
                detail="stock_symbol is required. Provide a symbol like 'AAPL' or 'RELIANCE.NS'."
            )

        stock_symbol, market = validate_and_normalize_symbol(stock_symbol, market)
        
        logger.info(
            f"Chat request",
            extra={
                "symbol": stock_symbol,
                "market": market,
                "message_preview": request.message[:50]
            }
        )
        
        # Check cache
        cache_key = make_chat_cache_key(stock_symbol, request.message)
        
        if cache_service:
            cached_response = await cache_service.get(cache_key)
            if cached_response:
                logger.info(f"Cache hit for chat: {stock_symbol}")
                return ChatResponse(**cached_response)
        
        # Execute crew analysis
        result = await crew_service.execute_chat_query(
            message=request.message,
            stock_symbol=stock_symbol,
            market=market
        )
        
        # Build response
        response = ChatResponse(
            response=result.get("response", "Unable to generate response."),
            sources=result.get("sources", []),
            agent_reasoning=result.get("agent_reasoning"),
            stock_symbol=stock_symbol,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Cache the response
        if cache_service:
            await cache_service.set(
                cache_key,
                response.model_dump(),
                ttl=settings.CACHE_TTL_CHAT
            )
        
        logger.info(f"Chat response generated for {stock_symbol}")
        return response
        
    except ValueError as e:
        # Validation error
        logger.warning(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
        
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to process your question. Please try again."
        )


@router.get("/chat/health")
async def chat_health():
    """
    Health check for chat endpoint.
    """
    return {
        "status": "healthy",
        "endpoint": "chat",
        "features": ["stock_qa", "news_summary", "metrics_analysis"]
    }
