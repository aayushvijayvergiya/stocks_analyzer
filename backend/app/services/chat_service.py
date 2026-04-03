"""
Chat Service — executes the chat crew with intent-driven task selection.
"""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import uuid
from crewai import Crew, Process

from app.crew.agents import FinancialAgents
from app.crew.tasks import FinancialTasks
from app.crew.output_models import ChatAnswerOutput
from app.services.job_store import JobStore
from app.services.intent_classifier import classify_intent
from app.utils.logger import get_logger
from app.utils.exceptions import CrewExecutionError

logger = get_logger(__name__)

CHAT_TIMEOUT = 30


class ChatService:
    """Executes the chat crew asynchronously with intent-driven task selection."""

    def __init__(self, job_store: Optional[JobStore] = None):
        self.job_store = job_store

    async def execute_chat_query(
        self,
        message: str,
        stock_symbol: str,
        market: str,
        job_id: Optional[str] = None
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
            await self.job_store.update_job(job_id, "processing", "Initializing agents...")

        try:
            market_researcher = FinancialAgents.market_researcher()
            data_analyst = FinancialAgents.financial_data_analyst()
            advisor = FinancialAgents.investment_advisor()

            if self.job_store:
                await self.job_store.update_job(job_id, "processing", "Classifying query intent...")

            intent = await classify_intent(message)
            logger.info(f"Classified intent: {intent}")

            tasks = []

            if self.job_store:
                await self.job_store.update_job(job_id, "processing", "Analyzing financial data...")

            if intent["needs_news"]:
                tasks.append(FinancialTasks.research_stock_news(
                    market_researcher, stock_symbol, stock_symbol
                ))

            if intent["needs_metrics"]:
                tasks.append(FinancialTasks.analyze_stock_financials(
                    data_analyst, stock_symbol, market
                ))

            if not tasks:
                tasks.append(FinancialTasks.analyze_stock_financials(
                    data_analyst, stock_symbol, market
                ))

            if self.job_store:
                await self.job_store.update_job(job_id, "processing", "Synthesizing response...")

            tasks.append(FinancialTasks.synthesize_chat_response(
                advisor, message, stock_symbol, market
            ))

            crew = Crew(
                agents=[market_researcher, data_analyst, advisor],
                tasks=tasks,
                process=Process.sequential,
                verbose=True,
                memory=False,
                cache=True,
            )

            result = await self._run_crew_with_timeout(crew, timeout=CHAT_TIMEOUT)

            output: ChatAnswerOutput = result.pydantic
            response_data = {
                "response": output.response,
                "sources": [s.model_dump() for s in output.sources],
                "agent_reasoning": output.agent_reasoning,
                "stock_symbol": stock_symbol,
                "timestamp": datetime.now(timezone.utc).isoformat()
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

    async def _run_crew_with_timeout(self, crew: Crew, timeout: int):
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, crew.kickoff),
            timeout=timeout
        )
