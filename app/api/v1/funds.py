"""
Fund/ETF Recommendations API - Get top fund picks by top sectors.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks

from app.models.requests import FundRecommendationParams
from app.models.responses import FundRecommendationResponse, JobStatus
from app.services import CacheService, CrewService, JobStore, make_fund_cache_key
from app.dependencies import get_cache_service, get_crew_service, get_job_store, check_rate_limit
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


async def run_fund_analysis_background(
    job_id: str,
    market: str,
    timeframe: str,
    crew_service: CrewService,
    cache_service: CacheService 
):
    """
    Background task to run fund analysis crew.
    
    This runs asynchronously and updates job status via JobStore.
    """
    try:
        logger.info(f"Starting background fund analysis: {job_id}")
        
        # Execute crew
        result = await crew_service.execute_fund_recommendations(
            market=market,
            timeframe=timeframe,
            job_id=job_id
        )
        
        # Cache the result
        if cache_service:
            cache_key = make_fund_cache_key(timeframe, str(market))
            await cache_service.set(
                cache_key,
                result,
                ttl=settings.CACHE_TTL_STOCKS  # Same TTL as stocks
            )
        
        logger.info(f"Completed fund analysis: {job_id}")
        
    except Exception as e:
        logger.error(f"Background fund analysis failed: {job_id}: {e}", exc_info=True)
        # Error already tracked in crew_service via job_store


@router.post("/recommendations", response_model=FundRecommendationResponse)
async def create_fund_recommendations(
    params: FundRecommendationParams,
    background_tasks: BackgroundTasks,
    cache_service: CacheService = Depends(get_cache_service),
    crew_service: CrewService = Depends(get_crew_service),
    job_store: JobStore = Depends(get_job_store),
    _ = Depends(check_rate_limit)
):
    """
    Create a fund/ETF recommendation analysis job.
    
    This endpoint analyzes top-performing sectors and recommends ETFs (US) or
    sectoral indices (India) for investment.
    
    **Note for India Market:**
    Direct mutual fund data is limited. Currently showing:
    - Nifty sectoral indices (Nifty IT, Nifty Bank, etc.)
    - Index funds and sectoral ETFs where available
    - Full mutual fund support coming in future update
    
    **Process:**
    1. POST /funds/recommendations → Returns job_id immediately
    2. GET /funds/recommendations/{job_id} → Poll for status
    3. When completed, result contains fund recommendations
    
    **Analysis includes:**
    - Top 3 performing sectors (based on timeframe)
    - Top 3 fund/ETF picks per sector
    - Expense ratios, AUM, performance metrics
    - Sector trends and outlook
    
    **Timeframes:**
    - `7d`: Last 7 days performance
    - `30d`: Last 30 days (default)
    - `90d`: Last 90 days
    
    **Markets:**
    - `US`: US ETFs (sector ETFs like XLK, XLF, etc.)
    - `IN`: India sectoral indices and ETFs
    - `ALL`: Combined analysis
    
    **Cache:** Results cached for 30 minutes
    
    **Expected Time:** 30-90 seconds for completion
    """
    try:
        logger.info(
            f"Fund recommendations request",
            extra={
                "market": params.market,
                "timeframe": params.timeframe,
                "fund_type": params.fund_type
            }
        )
        
        # Check cache first
        market_value = params.market or "ALL"
        cache_key = make_fund_cache_key(params.timeframe, market_value)
        
        if cache_service:
            cached_result = await cache_service.get(cache_key)
            if cached_result:
                logger.info(f"Cache hit for fund recommendations: {cache_key}")
                cached_result["cache_hit"] = True
                return FundRecommendationResponse(**cached_result)
        
        # Create job
        job_id = str(uuid.uuid4())
        
        if job_store:
            await job_store.create_job(job_id, "fund_recommendations")
        
        # Start background analysis
        market_value = params.market or "ALL"
        background_tasks.add_task(
            run_fund_analysis_background,
            job_id=job_id,
            market=market_value,
            timeframe=params.timeframe,
            crew_service=crew_service,
            cache_service=cache_service
        )
        
        # Return immediately with job info
        response = FundRecommendationResponse(
            job_id=job_id,
            status="pending",
            generated_at=None,
            timeframe=params.timeframe,
            market=market_value,
            top_sectors=None,
            analysis_summary=None,
            cache_hit=False,
            note="India mutual fund recommendations coming soon. Currently showing sectoral indices and ETF proxies."
        )
        
        logger.info(f"Created fund recommendations job: {job_id}")
        return response
        
    except Exception as e:
        logger.error(f"Fund recommendations error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to create fund analysis. Please try again."
        )


@router.get("/recommendations/{job_id}", response_model=JobStatus)
async def get_fund_recommendations_status(
    job_id: str,
    job_store: JobStore = Depends(get_job_store)
):
    """
    Get status of a fund recommendations job.
    
    Poll this endpoint to check if your fund analysis is complete.
    
    **Status Values:**
    - `pending`: Job created, waiting to start
    - `processing`: Analysis in progress
    - `completed`: Analysis done, `result` contains recommendations
    - `failed`: Analysis failed, `error` contains error message
    
    **Polling Strategy:**
    - Poll every 2-3 seconds
    - Stop when status is `completed` or `failed`
    - Max wait time: ~90 seconds
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
        logger.error(f"Get fund job status error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve job status"
        )


@router.get("/recommendations/health")
async def fund_recommendations_health():
    """
    Health check for fund recommendations endpoint.
    """
    return {
        "status": "healthy",
        "endpoint": "fund_recommendations",
        "features": ["sector_etf_analysis", "fund_ranking", "job_polling"],
        "note": "India mutual fund support in development"
    }
