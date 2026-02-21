from redis.asyncio import Redis
from redis.exceptions import RedisError
import uuid
import json
from datetime import datetime, timezone
from typing import Optional

from app.models.responses import JobStatus
from app.utils.logger import get_logger

logger = get_logger(__name__)

class JobStore:
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.job_prefix = "job:"
        self.job_ttl = 3600  # Jobs expire after 1 hour
    
    async def create_job(self, job_id: str = '', job_type: str = "unknown") -> str:
        """Create a new job and return its ID.
        
        Args:
            job_id: Optional job ID to use (generates UUID if not provided)
            job_type: Type of job (e.g., 'chat', 'stock_recommendations')
            
        Returns:
            Job ID (UUID string)
        """
        if not job_id:
            job_id = str(uuid.uuid4())
        
        job_data = {
            "job_id": job_id,
            "type": job_type,
            "status": "pending",
            "progress": "Initializing...",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "result": None,
            "error": None
        }
        
        key = f"{self.job_prefix}{job_id}"
        await self.redis.set(key, json.dumps(job_data), ex=self.job_ttl)
        
        logger.info(f"Created job {job_id} of type {job_type}")
        return job_id
    
    
    async def update_job(
        self,
        job_id: str,
        status: str,
        progress: str = '',
        result: dict = {},
        error: str = ''
    ) -> bool:
        """Update job status and progress.
        
        Args:
            job_id: Job ID to update
            status: New status ('pending', 'processing', 'completed', 'failed')
            progress: Progress message (optional)
            result: Result data (optional, for completed jobs)
            error: Error message (optional, for failed jobs)
            
        Returns:
            True if updated successfully, False otherwise
        """
        key = f"{self.job_prefix}{job_id}"
        try:
            job_data_str = await self.redis.get(key)
        except RedisError:
            logger.warning("Cache get failed", extra={"key": key})
            return False
        
        if not job_data_str:
            logger.info("Job not found for update", extra={"job_id": job_id})
            return False
        
        try:
            job_data = json.loads(job_data_str)
        except json.JSONDecodeError:
            logger.error("Failed to decode job data", extra={"job_id": job_id})
            return False
        
        # Update fields
        job_data["status"] = status
        
        if progress is not None:
            job_data["progress"] = progress
        
        if result is not None:
            job_data["result"] = result
        
        if error is not None:
            job_data["error"] = error
        
        if status in ["completed", "failed"]:
            job_data["completed_at"] = datetime.now(timezone.utc).isoformat()
        
        await self.redis.set(key, json.dumps(job_data), ex=self.job_ttl)
        logger.info(f"Updated job {job_id} to status {status}")
        return True
    
    
    async def get_job(self, job_id: str) -> Optional[dict]:
        """Get job status and data.
        
        Args:
            job_id: Job ID to retrieve
            
        Returns:
            Job data dict or None if not found
        """
        key = f"{self.job_prefix}{job_id}"
        try:
            job_data_str = await self.redis.get(key)
        except RedisError:
            logger.warning("Cache get failed", extra={"key": key})
            return None
        
        if not job_data_str:
            logger.info("Job not found", extra={"job_id": job_id})
            return None
        
        try:
            job_data = json.loads(job_data_str)
            return job_data
        except json.JSONDecodeError:
            logger.warning("Job data deserialization failed", extra={"job_id": job_id})
            return None