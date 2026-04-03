"""
Stock Recommendations API - Get top stock picks by top sectors.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import Literal

from datetime import datetime, timezone

from app.models.requests import StockRecommendationParams
from app.models.responses import StockRecommendationResponse, JobStatus
from app.services import CacheService, CrewService, JobStore, make_stock_cache_key
from app.dependencies import get_cache_service, get_crew_service, get_job_store, check_rate_limit
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


async def run_stock_analysis_background(
    job_id: str,
    market: str,
    timeframe: str,
    crew_service: CrewService,
    cache_service: CacheService
):
    """
    Background task to run stock analysis crew.
    
    This runs asynchronously and updates job status via JobStore.
    """
    try:
        logger.info(f"Starting background stock analysis: {job_id}")
        
        # Execute crew
        result = await crew_service.execute_stock_recommendations(
            market=market,
            timeframe=timeframe,
            job_id=job_id
        )
        
        # Cache the result
        if cache_service:
            cache_key = make_stock_cache_key(timeframe, market)
            await cache_service.set(
                cache_key,
                result,
                ttl=settings.CACHE_TTL_STOCKS
            )
        
        logger.info(f"Completed stock analysis: {job_id}")
        
    except Exception as e:
        logger.error(f"Background stock analysis failed: {job_id}: {e}", exc_info=True)
        # Error already tracked in crew_service via job_store


@router.post("/recommendations", response_model=StockRecommendationResponse)
async def create_stock_recommendations(
    params: StockRecommendationParams,
    background_tasks: BackgroundTasks,
    cache_service: CacheService = Depends(get_cache_service),
    crew_service: CrewService = Depends(get_crew_service),
    job_store: JobStore = Depends(get_job_store),
    _ = Depends(check_rate_limit)
):
    """
    Create a stock recommendation analysis job.
    
    This endpoint initiates a comprehensive analysis of top sectors and stocks.
    Due to the complexity of the analysis, this returns immediately with a job_id.
    Use the GET /recommendations/{job_id} endpoint to poll for results.
    
    **Process:**
    1. POST /recommendations → Returns job_id immediately
    2. GET /recommendations/{job_id} → Poll for status (pending/processing/completed)
    3. When completed, result contains full recommendations
    
    **Analysis includes:**
    - Top 3 performing sectors (based on timeframe)
    - Top 3 stock picks per sector (9 total stocks)
    - Financial metrics, performance data, reasoning
    - Market sentiment and news analysis
    
    **Timeframes:**
    - `7d`: Last 7 days performance
    - `30d`: Last 30 days (default)
    - `90d`: Last 90 days
    
    **Markets:**
    - `US`: US stocks (NYSE, NASDAQ)
    - `IN`: India stocks (NSE, BSE)
    - `ALL`: Combined analysis
    
    **Cache:** Results cached for 30 minutes per market+timeframe combo
    
    **Expected Time:** 30-90 seconds for completion
    """
    try:
        logger.info(
            f"Stock recommendations request",
            extra={
                "market": params.market,
                "timeframe": params.timeframe
            }
        )
        
        # Check cache first
        market_value = params.market or "ALL"
        cache_key = make_stock_cache_key(params.timeframe, market_value)
        
        if cache_service:
            cached_result = await cache_service.get(cache_key)
            if cached_result:
                logger.info(f"Cache hit for stock recommendations: {cache_key}")
                # Return cached result with cache_hit flag
                cached_result["cache_hit"] = True
                return StockRecommendationResponse(**cached_result)
        
        # Create job
        job_id = str(uuid.uuid4())

        if job_store:
            await job_store.create_job(job_id, "stock_recommendations")

        # Start background analysis
        background_tasks.add_task(
            run_stock_analysis_background,
            job_id=job_id,
            market=market_value,
            timeframe=params.timeframe,
            crew_service=crew_service,
            cache_service=cache_service
        )
        
        # Return immediately with job info
        response = StockRecommendationResponse(
            job_id=job_id,
            status="pending",
            generated_at=datetime.now(timezone.utc),
            timeframe=params.timeframe,
            region=market_value,
            top_sectors=None,
            analysis_summary=None,
            cache_hit=False
        )
        
        logger.info(f"Created stock recommendations job: {job_id}")
        return response
        
    except Exception as e:
        logger.error(f"Stock recommendations error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to create recommendation analysis. Please try again."
        )


@router.get("/recommendations/{job_id}", response_model=JobStatus)
async def get_stock_recommendations_status(
    job_id: str,
    job_store: JobStore = Depends(get_job_store)
):
    """
    Get status of a stock recommendations job.
    
    Poll this endpoint to check if your analysis is complete.
    
    **Status Values:**
    - `pending`: Job created, waiting to start
    - `processing`: Analysis in progress (check `progress` field for details)
    - `completed`: Analysis done, `result` contains recommendations
    - `failed`: Analysis failed, `error` contains error message
    
    **Polling Strategy:**
    - Poll every 2-3 seconds
    - Stop when status is `completed` or `failed`
    - Max wait time: ~90 seconds
    
    **Response Fields:**
    - `job_id`: Your job identifier
    - `status`: Current status
    - `progress`: Human-readable progress message
    - `created_at`: When job was created
    - `completed_at`: When job finished (null if not done)
    - `result`: Full recommendation data (null until completed)
    - `error`: Error message (null unless failed)
    """
    try:
        if not job_store:
            raise HTTPException(
                status_code=503,
                detail="Job tracking unavailable (Redis connection issue)"
            )
        
        job_data = await job_store.get_job(job_id)
        
        if not job_data:
            raise HTTPException(
                status_code=404,
                detail=f"Job {job_id} not found. Jobs expire after 1 hour."
            )
        
        return JobStatus(**job_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get job status error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve job status"
        )


@router.get("/recommendations/health")
async def stock_recommendations_health():
    """
    Health check for stock recommendations endpoint.
    """
    return {
        "status": "healthy",
        "endpoint": "stock_recommendations",
        "features": ["sector_analysis", "stock_ranking", "job_polling"]
    }
