from typing import AsyncGenerator, Optional
from fastapi import Depends, Request, HTTPException
from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool

from app.config import settings
from app.services.cache import CacheService
from app.services.job_store import JobStore
from app.services.crew_service import CrewService
from app.utils.exceptions import RateLimitError

redis_pool: Optional[ConnectionPool] = None

async def init_redis_pool() -> None:
    global redis_pool
    if redis_pool is None:
        redis_pool = ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=10,
            decode_responses=True
        )
        

async def close_redis_pool() -> None:
    global redis_pool
    if redis_pool:
        await redis_pool.disconnect()
        
        
async def get_redis() -> Optional[Redis]:
    if redis_pool is None:
        return None
    
    try:
        return Redis(connection_pool=redis_pool)
    except Exception:
        return None
    
    
async def get_cache_service(redis: Redis = Depends(get_redis)) -> Optional[CacheService]:
    if redis is None:
        return None
    return CacheService(redis_client=redis)


async def get_job_store(redis: Redis = Depends(get_redis)) -> Optional[JobStore]:
    if redis is None:
        return None
    return JobStore(redis_client=redis)


async def get_crew_service(job_store: JobStore = Depends(get_job_store)) -> CrewService:
    """Get CrewService instance with job tracking.
    
    Returns:
        CrewService instance (with or without job_store depending on Redis availability)
    """
    return CrewService(job_store=job_store)


async def get_redis_state(redis: Redis = Depends(get_redis)) -> AsyncGenerator[Optional[Redis], None]:
    """
    Async generator that yields Redis client from app state.
    Returns None if Redis is unavailable.
    """
    redis_client: Optional[Redis] = None
    try:
        redis_client = redis
        if redis_client is not None:
            # Test connection
            redis_client.ping()
        yield redis_client
    except Exception:
        # Handle connection errors gracefully
        yield None


async def check_rate_limit(request: Request, redis: Redis = Depends(get_redis)) -> None:
    """
    Rate limiter dependency that will use Redis to track request counts.
    Currently a pass-through placeholder.
    """
    redis_client: Optional[Redis] = redis
    if redis_client is None:
        # If Redis is unavailable, skip rate limiting
        return
    
    client_ip = request.client.host if request.client else "unknown"
    endpoint = request.url.path
    rate_limit_key = f"rate_limit:{client_ip}:{endpoint}"
    
    try:
        request_count = await redis_client.incr(rate_limit_key)
        if request_count == 1:
            await redis_client.expire(rate_limit_key, settings.RATE_LIMIT_WINDOW) 
        
        if request_count > settings.RATE_LIMIT_REQUESTS:  # 100 requests per minute
            raise RateLimitError(
                limit=settings.RATE_LIMIT_REQUESTS,
                window=settings.RATE_LIMIT_WINDOW
            )
    except RateLimitError:
        raise
    except Exception:
        # If Redis fails, allow the request
        pass