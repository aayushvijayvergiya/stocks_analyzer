"""
CrewService — backward-compatible facade over ChatService and RecommendationsService.

Existing consumers (dependencies.py, tests) continue to import CrewService unchanged.
New code should import ChatService or RecommendationsService directly.
"""

from typing import Optional, Dict, Any
from app.services.chat_service import ChatService
from app.services.recommendations_service import RecommendationsService
from app.services.job_store import JobStore
from app.utils.exceptions import CrewExecutionError  # re-export for backward compat


class CrewService:
    """Thin facade combining ChatService and RecommendationsService."""

    def __init__(self, job_store: Optional[JobStore] = None):
        self._chat = ChatService(job_store=job_store)
        self._recommendations = RecommendationsService(job_store=job_store)
        self.job_store = job_store

    async def execute_chat_query(self, *args, **kwargs) -> Dict[str, Any]:
        return await self._chat.execute_chat_query(*args, **kwargs)

    async def execute_stock_recommendations(self, *args, **kwargs) -> Dict[str, Any]:
        return await self._recommendations.execute_stock_recommendations(*args, **kwargs)

    async def execute_fund_recommendations(self, *args, **kwargs) -> Dict[str, Any]:
        return await self._recommendations.execute_fund_recommendations(*args, **kwargs)
