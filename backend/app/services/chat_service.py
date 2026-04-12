"""
Chat Service — prefetches data, then runs a chat-synthesis crew in a subprocess.
"""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import uuid

from app.crew.output_models import ChatAnswerOutput
from app.services.job_store import JobStore
from app.services.crew_runner import run_with_cancellation
from app.services.data_fetchers import fetch_stock_snapshot_sync, fetch_stock_news_sync
from app.services.intent_classifier import classify_intent
from app.config import settings
from app.utils.logger import get_logger
from app.utils.exceptions import CrewExecutionError

logger = get_logger(__name__)


class ChatService:
    """Executes the chat crew asynchronously over pre-fetched data."""

    def __init__(self, job_store: Optional[JobStore] = None):
        self.job_store = job_store

    async def execute_chat_query(
        self,
        message: str,
        stock_symbol: str,
        market: str,
        job_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute crew for chat endpoint.

        Args:
            message: User's question
            stock_symbol: Stock symbol to analyze
            market: "US" or "IN"
            job_id: Optional job ID for tracking

        Returns:
            Dict with response, sources, agent_reasoning, stock_symbol, timestamp
        """
        if not job_id:
            job_id = str(uuid.uuid4())

        if self.job_store:
            await self.job_store.create_job(job_id, "chat")
            await self.job_store.update_job(job_id, "processing", "Classifying intent...")

        try:
            intent = await classify_intent(message)
            logger.info(f"Classified intent: {intent}")

            loop = asyncio.get_running_loop()
            snapshot: Dict[str, Any] = {}
            news: list = []

            if self.job_store:
                await self.job_store.update_job(job_id, "processing", "Fetching stock data...")

            # Always fetch the snapshot — it's cheap and grounds the response.
            snapshot = await loop.run_in_executor(
                None, fetch_stock_snapshot_sync, stock_symbol, "30d"
            )

            if intent.get("needs_news"):
                if self.job_store:
                    await self.job_store.update_job(job_id, "processing", "Fetching news...")
                news = await loop.run_in_executor(
                    None, fetch_stock_news_sync, stock_symbol, 5
                )

            if self.job_store:
                await self.job_store.update_job(job_id, "processing", "Synthesizing response...")

            result_json = await run_with_cancellation(
                target_name="chat_crew",
                args={
                    "user_question": message,
                    "stock_symbol": stock_symbol,
                    "market": market,
                    "prefetched_snapshot": snapshot,
                    "prefetched_news": news,
                },
                timeout=settings.CREW_TIMEOUT_SECONDS,
            )
            output = ChatAnswerOutput.model_validate_json(result_json)

            response_data = {
                "response": output.response,
                "sources": [s.model_dump() for s in output.sources],
                "agent_reasoning": {"investment_advisor": output.agent_reasoning},
                "stock_symbol": stock_symbol,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            if self.job_store:
                await self.job_store.update_job(
                    job_id, "completed", "Analysis complete", result=response_data
                )

            logger.info(f"Chat query completed for {stock_symbol}")
            return response_data

        except asyncio.TimeoutError:
            error_msg = "Analysis timed out. Please try again."
            logger.error(f"Chat query timeout for {stock_symbol}")
            if self.job_store:
                await self.job_store.update_job(job_id, "failed", error=error_msg)
            raise CrewExecutionError(error_msg)

        except Exception as e:
            error_msg = f"Analysis failed: {str(e)}"
            logger.error(f"Chat query error for {stock_symbol}: {e}", exc_info=True)
            if self.job_store:
                await self.job_store.update_job(job_id, "failed", error=error_msg)
            raise CrewExecutionError(error_msg)
