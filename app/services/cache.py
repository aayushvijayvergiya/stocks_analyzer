from datetime import datetime
import json
from typing import Any, Optional

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.utils.logger import get_logger


logger = get_logger(__name__)


class CacheService:
    def __init__(self, redis_client: Redis) -> None:
        self.redis: Redis = redis_client

    async def set(self, key: str, value: dict[str, Any], ttl: int) -> bool:
        try:
            payload = json.dumps(value)
            return bool(await self.redis.set(key, payload, ex=ttl))
        except (RedisError, TypeError, ValueError):
            logger.warning("Cache set failed", extra={"key": key})
            return False

    async def get(self, key: str) -> Optional[dict[str, Any]]:
        try:
            val = await self.redis.get(key)
        except RedisError:
            logger.warning("Cache get failed", extra={"key": key})
            return None

        if not val:
            logger.info("Cache miss", extra={"key": key})
            return None

        try:
            data = json.loads(val)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            logger.warning("Cache deserialize failed", extra={"key": key})
            return None

        logger.info("Cache hit", extra={"key": key})
        return data
    

    async def delete(self, key: str) -> bool:
        try:
            return bool(await self.redis.delete(key))
        except RedisError:
            logger.warning("Cache delete failed", extra={"key": key})
            return False
        
    async def exists(self, key: str) -> bool:
        try:
            return bool(await self.redis.exists(key))
        except RedisError:
            logger.warning("Cache exists failed", extra={"key": key})
            return False

    async def clear(self):
        await self.redis.flushdb()
        
        
def get_cache_bucket(minutes: int = 30) -> str:
    """
    Round current time to nearest bucket for cache key generation.
    
    Example: 10:47 AM with 30-min bucket → "1030"
    """
    now = datetime.now()
    bucket_minutes = (now.minute // minutes) * minutes
    bucket_time = now.replace(minute=bucket_minutes, second=0, microsecond=0)
    return bucket_time.strftime("%H%M")


def make_stock_cache_key(timeframe: str, market: str) -> str:
    """Generate cache key for stock recommendations.
    
    Pattern: stocks:recommendations:{timeframe}:{market}:{timestamp_bucket}
    """
    bucket = get_cache_bucket()
    return f"stocks:recommendations:{timeframe}:{market}:{bucket}"

def make_fund_cache_key(timeframe: str, market: str) -> str:
    """Generate cache key for fund recommendations.
    
    Pattern: funds:recommendations:{timeframe}:{market}:{timestamp_bucket}
    """
    bucket = get_cache_bucket()
    return f"funds:recommendations:{timeframe}:{market}:{bucket}"

def make_chat_cache_key(stock_symbol: str, message: str) -> str:
    """Generate cache key for chat responses.
    """
    import hashlib

    message_hash = hashlib.md5(message.encode()).hexdigest()[:8]  # Shorten for readability
    return f"chat:{stock_symbol}:{message_hash}"


def make_news_cache_key(query: str, days_back: int) -> str:
    """Generate cache key for news queries.
    
    Pattern: news:{query_hash}:{days_back}:{date_bucket}
    Cache for 1 hour to avoid repeated API calls.
    """
    import hashlib
    query_hash = hashlib.md5(query.encode()).hexdigest()[:12]
    date_bucket = datetime.now().strftime("%Y%m%d%H")  # Hourly bucket
    return f"news:{query_hash}:{days_back}:{date_bucket}"

def make_search_cache_key(query: str) -> str:
    """Generate cache key for web searches."""
    import hashlib
    query_hash = hashlib.md5(query.encode()).hexdigest()[:12]
    date_bucket = datetime.now().strftime("%Y%m%d%H")
    return f"search:{query_hash}:{date_bucket}"