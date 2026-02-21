"""
Main API v1 Router - Aggregates all endpoint routers.
"""

from fastapi import APIRouter

from app.api.v1 import chat, stocks, funds

# Create main v1 router
router = APIRouter()

# Include all sub-routers
router.include_router(
    chat.router,
    tags=["Chat"]
)

router.include_router(
    stocks.router,
    prefix="/stocks",
    tags=["Stock Recommendations"]
)

router.include_router(
    funds.router,
    prefix="/funds",
    tags=["Fund Recommendations"]
)


@router.get("/")
async def api_v1_root():
    """
    API v1 root endpoint.
    
    Provides information about available endpoints.
    """
    return {
        "message": "Stocks Analyzer API v1",
        "version": "1.0.0",
        "endpoints": {
            "chat": {
                "path": "/api/v1/chat",
                "method": "POST",
                "description": "Ask questions about specific stocks"
            },
            "stock_recommendations": {
                "create_job": {
                    "path": "/api/v1/stocks/recommendations",
                    "method": "POST",
                    "description": "Create stock recommendation analysis job"
                },
                "get_status": {
                    "path": "/api/v1/stocks/recommendations/{job_id}",
                    "method": "GET",
                    "description": "Get job status and results"
                }
            },
            "fund_recommendations": {
                "create_job": {
                    "path": "/api/v1/funds/recommendations",
                    "method": "POST",
                    "description": "Create fund recommendation analysis job"
                },
                "get_status": {
                    "path": "/api/v1/funds/recommendations/{job_id}",
                    "method": "GET",
                    "description": "Get job status and results"
                }
            }
        },
        "docs": "/docs",
        "openapi": "/api/v1/openapi.json"
    }
